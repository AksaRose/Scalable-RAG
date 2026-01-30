"""Embedding worker for generating vector embeddings."""
import sys
import os
import uuid
import time
import json
import logging
from pathlib import Path
from typing import List, Dict, Any

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import psycopg2
from psycopg2.extras import RealDictCursor
import pandas as pd
from sentence_transformers import SentenceTransformer
from shared.config import config
from shared.queue import QueueClient
from services.storage import StorageService
from services.qdrant_client import QdrantService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class EmbedderWorker:
    """Worker for generating embeddings and storing in Qdrant."""
    
    def __init__(self):
        self.queue_client = QueueClient()
        self.storage_service = StorageService()
        self.qdrant_service = QdrantService()
        self.db_conn = psycopg2.connect(config.DATABASE_URL)
        
        # Load the embedding model (open-source)
        logger.info(f"Loading embedding model: {config.EMBEDDING_MODEL}")
        self.embedding_model = SentenceTransformer(config.EMBEDDING_MODEL)
        logger.info("Embedding model loaded successfully")
    
    def generate_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for a batch of texts.
        
        Args:
            texts: List of texts to embed
            
        Returns:
            List of embedding vectors
        """
        try:
            # Generate embeddings using sentence-transformers
            embeddings = self.embedding_model.encode(
                texts,
                batch_size=config.EMBEDDING_BATCH_SIZE,
                show_progress_bar=False,
                convert_to_numpy=True
            )
            # Convert to list of lists
            return embeddings.tolist()
        except Exception as e:
            logger.error(f"Error generating embeddings: {e}")
            raise
    
    def save_embeddings_to_parquet(self, embeddings_data: List[Dict[str, Any]], file_path: str):
        """Save embeddings to Parquet file for fault tolerance.
        
        Args:
            embeddings_data: List of dicts with chunk_id, vector, payload
            file_path: Path to save Parquet file
        """
        try:
            df = pd.DataFrame(embeddings_data)
            parquet_data = df.to_parquet()
            
            # Save to object storage
            self.storage_service.upload_file(
                parquet_data,
                file_path,
                content_type="application/octet-stream"
            )
            logger.info(f"Saved embeddings to Parquet: {file_path}")
        except Exception as e:
            logger.error(f"Error saving embeddings to Parquet: {e}")
            raise
    
    def create_job(self, tenant_id: str, document_id: str, job_type: str, status: str = "processing") -> str:
        """Create a job record in the database."""
        job_id = uuid.uuid4()
        with self.db_conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                INSERT INTO jobs (job_id, tenant_id, document_id, job_type, status)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING job_id
                """,
                (str(job_id), tenant_id, document_id, job_type, status)
            )
            self.db_conn.commit()
        return str(job_id)
    
    def update_job_status(self, job_id: str, status: str, error_message: str = None):
        """Update job status."""
        with self.db_conn.cursor() as cur:
            cur.execute(
                """
                UPDATE jobs
                SET status = %s, error_message = %s, updated_at = CURRENT_TIMESTAMP
                WHERE job_id = %s
                """,
                (status, error_message, job_id)
            )
            self.db_conn.commit()
    
    def update_chunk_embedding_path(self, chunk_id: str, embedding_path: str):
        """Update chunk with embedding path."""
        with self.db_conn.cursor() as cur:
            cur.execute(
                """
                UPDATE chunks
                SET embedding_path = %s
                WHERE chunk_id = %s
                """,
                (embedding_path, chunk_id)
            )
            self.db_conn.commit()
    
    def process_job(self, job_data: dict):
        """Process an embedding job with retry logic."""
        tenant_id = job_data['tenant_id']
        document_id = job_data['document_id']
        payload = job_data['payload']
        chunk_path = payload['chunk_path']
        chunk_id = payload['chunk_id']
        filename = payload['filename']
        
        job_id = None
        max_retries = config.MAX_RETRIES
        retry_count = 0
        
        while retry_count <= max_retries:
            try:
                # Create job record (only on first attempt)
                if retry_count == 0:
                    job_id = self.create_job(tenant_id, document_id, "embed", "processing")
                else:
                    # Update retry count
                    with self.db_conn.cursor() as cur:
                        cur.execute(
                            """
                            UPDATE jobs
                            SET retry_count = %s, status = 'processing', updated_at = CURRENT_TIMESTAMP
                            WHERE job_id = %s
                            """,
                            (retry_count, job_id)
                        )
                        self.db_conn.commit()
                
                # Download chunk text
                logger.info(f"Generating embedding for chunk {chunk_id} (document_id: {document_id}, attempt: {retry_count + 1})")
                chunk_data = self.storage_service.download_file(chunk_path)
                chunk_text = chunk_data.decode('utf-8')
                
                # Generate embedding
                embeddings = self.generate_embeddings([chunk_text])
                embedding_vector = embeddings[0]
                
                # Get chunk metadata from database
                with self.db_conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(
                        """
                        SELECT chunk_id, chunk_index, text
                        FROM chunks
                        WHERE chunk_id = %s
                        """,
                        (chunk_id,)
                    )
                    chunk_info = cur.fetchone()
                
                if not chunk_info:
                    raise ValueError(f"Chunk {chunk_id} not found in database")
                
                # Prepare point for Qdrant
                point = {
                    'id': chunk_id,
                    'vector': embedding_vector,
                    'payload': {
                        'tenant_id': tenant_id,
                        'document_id': str(document_id),
                        'chunk_id': chunk_id,
                        'text': chunk_text,
                        'filename': filename,
                        'chunk_index': chunk_info['chunk_index'],
                        'metadata': {
                            'chunk_index': chunk_info['chunk_index']
                        }
                    }
                }
                
                # Batch insert to Qdrant (single point for now, but could batch multiple)
                self.qdrant_service.upsert_points([point], tenant_id)
                
                # Save embedding to Parquet for fault tolerance
                parquet_path = f"{tenant_id}/{document_id}/embeddings/{chunk_id}.parquet"
                self.save_embeddings_to_parquet(
                    [{
                        'chunk_id': chunk_id,
                        'vector': embedding_vector,
                        'payload': point['payload']
                    }],
                    parquet_path
                )
                
                # Update chunk with embedding path
                self.update_chunk_embedding_path(chunk_id, parquet_path)
                
                # Mark job as completed
                self.update_job_status(job_id, "completed")
                
                # Check if all chunks for this document are embedded
                with self.db_conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT COUNT(*) as total, COUNT(embedding_path) as embedded
                        FROM chunks
                        WHERE document_id = %s
                        """,
                        (document_id,)
                    )
                    result = cur.fetchone()
                    total = result[0]
                    embedded = result[1]
                    
                    if total == embedded:
                        # All chunks embedded, mark document as completed
                        cur.execute(
                            """
                            UPDATE documents
                            SET status = 'completed', updated_at = CURRENT_TIMESTAMP
                            WHERE document_id = %s
                            """,
                            (document_id,)
                        )
                        self.db_conn.commit()
                        logger.info(f"Document {document_id} processing completed")
                
                logger.info(f"Successfully generated embedding for chunk {chunk_id}")
                return  # Success, exit retry loop
                
            except Exception as e:
                retry_count += 1
                logger.error(f"Error processing embedding job (attempt {retry_count}/{max_retries + 1}): {e}")
                
                if retry_count > max_retries:
                    # Max retries exceeded
                    if job_id:
                        self.update_job_status(job_id, "failed", str(e))
                    logger.error(f"Failed to process embedding job after {max_retries + 1} attempts")
                    return
                else:
                    # Exponential backoff
                    backoff_time = config.RETRY_BACKOFF_BASE ** retry_count
                    logger.info(f"Retrying in {backoff_time} seconds...")
                    time.sleep(backoff_time)
    
    def run(self):
        """Run the worker loop."""
        logger.info("Embedding worker started")
        
        while True:
            try:
                # Dequeue job
                job_data = self.queue_client.dequeue_job("embed")
                
                if job_data:
                    self.process_job(job_data)
                else:
                    time.sleep(1)
            except KeyboardInterrupt:
                logger.info("Worker stopped by user")
                break
            except Exception as e:
                logger.error(f"Error in worker loop: {e}")
                time.sleep(5)


if __name__ == "__main__":
    worker = EmbedderWorker()
    worker.run()
