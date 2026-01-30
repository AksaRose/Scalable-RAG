"""Chunking worker for text segmentation."""
import sys
import os
import uuid
import time
import json
import logging
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import psycopg2
from psycopg2.extras import RealDictCursor
from shared.config import config
from shared.queue import QueueClient
from services.storage import StorageService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ChunkerWorker:
    """Worker for chunking text into overlapping segments."""
    
    def __init__(self):
        self.queue_client = QueueClient()
        self.storage_service = StorageService()
        self.db_conn = psycopg2.connect(config.DATABASE_URL)
    
    def chunk_text(self, text: str, chunk_size: int = None, overlap: int = None) -> list[dict]:
        """Chunk text into overlapping segments.
        
        Args:
            text: Text to chunk
            chunk_size: Size of each chunk in characters (approximate)
            overlap: Overlap size in characters
            
        Returns:
            List of chunk dictionaries with text and metadata
        """
        if chunk_size is None:
            chunk_size = config.CHUNK_SIZE * 4  # Approximate: 1 token ≈ 4 characters
        if overlap is None:
            overlap = config.CHUNK_OVERLAP * 4
        
        chunks = []
        start = 0
        chunk_index = 0
        
        while start < len(text):
            end = start + chunk_size
            
            # Extract chunk
            chunk_text = text[start:end]
            
            # Try to break at sentence boundary if possible
            if end < len(text):
                # Look for sentence endings
                for i in range(min(200, len(text) - end), 0, -1):
                    if text[end + i - 1] in '.!?\n':
                        end = end + i
                        chunk_text = text[start:end]
                        break
            
            if chunk_text.strip():  # Only add non-empty chunks
                chunks.append({
                    'text': chunk_text.strip(),
                    'chunk_index': chunk_index,
                    'start_char': start,
                    'end_char': end
                })
                chunk_index += 1
            
            # Move start position with overlap
            start = end - overlap
            if start < 0:
                start = 0
        
        return chunks
    
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
    
    def process_job(self, job_data: dict):
        """Process a chunking job with retry logic."""
        tenant_id = job_data['tenant_id']
        document_id = job_data['document_id']
        payload = job_data['payload']
        text_path = payload['text_path']
        filename = payload['filename']
        
        job_id = None
        max_retries = config.MAX_RETRIES
        retry_count = 0
        
        while retry_count <= max_retries:
            try:
                # Create job record (only on first attempt)
                if retry_count == 0:
                    job_id = self.create_job(tenant_id, document_id, "chunk", "processing")
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
                
                # Download extracted text
                logger.info(f"Chunking text for {filename} (document_id: {document_id}, attempt: {retry_count + 1})")
                text_data = self.storage_service.download_file(text_path)
                text = text_data.decode('utf-8')
                
                # Chunk the text
                chunks = self.chunk_text(text)
                
                # Save chunks to database and storage
                chunk_paths = []
                for chunk in chunks:
                    chunk_id = uuid.uuid4()
                    
                    # Save chunk text to storage
                    chunk_path = f"{tenant_id}/{document_id}/chunks/{chunk_id}.txt"
                    self.storage_service.upload_file(
                        chunk['text'].encode('utf-8'),
                        chunk_path,
                        content_type="text/plain"
                    )
                    chunk_paths.append(chunk_path)
                    
                    # Save chunk to database
                    with self.db_conn.cursor() as cur:
                        cur.execute(
                            """
                            INSERT INTO chunks (chunk_id, document_id, tenant_id, chunk_index, text, embedding_path)
                            VALUES (%s, %s, %s, %s, %s, %s)
                            """,
                            (
                                str(chunk_id),
                                document_id,
                                tenant_id,
                                chunk['chunk_index'],
                                chunk['text'],
                                None  # embedding_path will be set by embedder
                            )
                        )
                
                self.db_conn.commit()
                
                # Mark job as completed
                self.update_job_status(job_id, "completed")
                
                # Enqueue embedding jobs for all chunks
                for chunk_path in chunk_paths:
                    # Extract chunk_id from path
                    chunk_filename = os.path.basename(chunk_path)
                    chunk_id = os.path.splitext(chunk_filename)[0]
                    
                    self.queue_client.enqueue_job(
                        job_type="embed",
                        tenant_id=tenant_id,
                        document_id=document_id,
                        payload={
                            "chunk_path": chunk_path,
                            "chunk_id": chunk_id,
                            "filename": filename
                        }
                    )
                
                logger.info(f"Successfully chunked {len(chunks)} chunks from {filename}")
                return  # Success, exit retry loop
                
            except Exception as e:
                retry_count += 1
                logger.error(f"Error processing chunking job (attempt {retry_count}/{max_retries + 1}): {e}")
                
                if retry_count > max_retries:
                    # Max retries exceeded
                    if job_id:
                        self.update_job_status(job_id, "failed", str(e))
                    logger.error(f"Failed to process chunking job after {max_retries + 1} attempts")
                    return
                else:
                    # Exponential backoff
                    backoff_time = config.RETRY_BACKOFF_BASE ** retry_count
                    logger.info(f"Retrying in {backoff_time} seconds...")
                    time.sleep(backoff_time)
    
    def run(self):
        """Run the worker loop."""
        logger.info("Chunking worker started")
        
        while True:
            try:
                # Dequeue job
                job_data = self.queue_client.dequeue_job("chunk")
                
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
    worker = ChunkerWorker()
    worker.run()
