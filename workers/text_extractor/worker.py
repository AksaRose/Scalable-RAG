"""Text extraction worker for PDF and TXT files."""
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
from api.services.storage import StorageService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TextExtractorWorker:
    """Worker for extracting text from PDF and TXT files."""
    
    def __init__(self):
        self.queue_client = QueueClient()
        self.storage_service = StorageService()
        self.db_conn = psycopg2.connect(config.DATABASE_URL)
    
    def extract_text_from_pdf(self, file_data: bytes) -> str:
        """Extract text from PDF file.
        
        Args:
            file_data: PDF file data as bytes
            
        Returns:
            Extracted text
        """
        try:
            from pypdf import PdfReader
            import io
            
            pdf_file = io.BytesIO(file_data)
            reader = PdfReader(pdf_file)
            
            text = ""
            for page in reader.pages:
                text += page.extract_text() + "\n"
            
            return text
        except Exception as e:
            logger.error(f"Error extracting text from PDF: {e}")
            raise
    
    def extract_text_from_txt(self, file_data: bytes) -> str:
        """Extract text from TXT file.
        
        Args:
            file_data: TXT file data as bytes
            
        Returns:
            Extracted text
        """
        try:
            # Try UTF-8 first
            return file_data.decode('utf-8')
        except UnicodeDecodeError:
            # Fallback to latin-1
            return file_data.decode('latin-1', errors='ignore')
    
    def extract_text(self, file_path: str, filename: str) -> str:
        """Extract text from file based on extension.
        
        Args:
            file_path: Path to file in storage
            filename: Original filename
            
        Returns:
            Extracted text
        """
        file_data = self.storage_service.download_file(file_path)
        file_ext = os.path.splitext(filename)[1].lower()
        
        if file_ext == '.pdf':
            return self.extract_text_from_pdf(file_data)
        elif file_ext == '.txt':
            return self.extract_text_from_txt(file_data)
        else:
            raise ValueError(f"Unsupported file type: {file_ext}")
    
    def create_job(self, tenant_id: str, document_id: str, job_type: str, status: str = "processing") -> str:
        """Create a job record in the database.
        
        Args:
            tenant_id: Tenant ID
            document_id: Document ID
            job_type: Type of job
            status: Job status
            
        Returns:
            Job ID
        """
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
        """Update job status.
        
        Args:
            job_id: Job ID
            status: New status
            error_message: Optional error message
        """
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
    
    def update_document_status(self, document_id: str, status: str):
        """Update document status.
        
        Args:
            document_id: Document ID
            status: New status
        """
        with self.db_conn.cursor() as cur:
            cur.execute(
                """
                UPDATE documents
                SET status = %s, updated_at = CURRENT_TIMESTAMP
                WHERE document_id = %s
                """,
                (status, document_id)
            )
            self.db_conn.commit()
    
    def process_job(self, job_data: dict):
        """Process an extraction job with retry logic.
        
        Args:
            job_data: Job data from queue
        """
        tenant_id = job_data['tenant_id']
        document_id = job_data['document_id']
        payload = job_data['payload']
        file_path = payload['file_path']
        filename = payload['filename']
        
        job_id = None
        max_retries = config.MAX_RETRIES
        retry_count = 0
        
        while retry_count <= max_retries:
            try:
                # Create job record (only on first attempt)
                if retry_count == 0:
                    job_id = self.create_job(tenant_id, document_id, "extract", "processing")
                    # Update document status
                    self.update_document_status(document_id, "processing")
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
                
                # Extract text
                logger.info(f"Extracting text from {filename} (document_id: {document_id}, attempt: {retry_count + 1})")
                text = self.extract_text(file_path, filename)
                
                # Save extracted text to storage
                text_path = f"{tenant_id}/{document_id}/extracted_text.txt"
                self.storage_service.upload_file(
                    text.encode('utf-8'),
                    text_path,
                    content_type="text/plain"
                )
                
                # Update document metadata
                with self.db_conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE documents
                        SET metadata = jsonb_build_object('text_path', %s, 'text_length', %s),
                            updated_at = CURRENT_TIMESTAMP
                        WHERE document_id = %s
                        """,
                        (text_path, len(text), document_id)
                    )
                    self.db_conn.commit()
                
                # Mark job as completed
                self.update_job_status(job_id, "completed")
                
                # Enqueue chunking job
                self.queue_client.enqueue_job(
                    job_type="chunk",
                    tenant_id=tenant_id,
                    document_id=document_id,
                    payload={"text_path": text_path, "filename": filename}
                )
                
                logger.info(f"Successfully extracted text from {filename}")
                return  # Success, exit retry loop
                
            except Exception as e:
                retry_count += 1
                logger.error(f"Error processing extraction job (attempt {retry_count}/{max_retries + 1}): {e}")
                
                if retry_count > max_retries:
                    # Max retries exceeded
                    if job_id:
                        self.update_job_status(job_id, "failed", str(e))
                    self.update_document_status(document_id, "failed")
                    logger.error(f"Failed to process extraction job after {max_retries + 1} attempts")
                    return
                else:
                    # Exponential backoff
                    backoff_time = config.RETRY_BACKOFF_BASE ** retry_count
                    logger.info(f"Retrying in {backoff_time} seconds...")
                    time.sleep(backoff_time)
    
    def run(self):
        """Run the worker loop."""
        logger.info("Text extraction worker started")
        
        while True:
            try:
                # Dequeue job (round-robin across tenants for fairness)
                job_data = self.queue_client.dequeue_job("extract")
                
                if job_data:
                    self.process_job(job_data)
                else:
                    # No jobs available, sleep briefly
                    time.sleep(1)
            except KeyboardInterrupt:
                logger.info("Worker stopped by user")
                break
            except Exception as e:
                logger.error(f"Error in worker loop: {e}")
                time.sleep(5)  # Wait before retrying


if __name__ == "__main__":
    worker = TextExtractorWorker()
    worker.run()
