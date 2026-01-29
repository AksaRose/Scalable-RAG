"""Object storage service for MinIO/S3."""
import io
from minio import Minio
from minio.error import S3Error
from shared.config import config
import logging

logger = logging.getLogger(__name__)


class StorageService:
    """Service for interacting with object storage."""
    
    def __init__(self):
        self.client = Minio(
            config.MINIO_ENDPOINT,
            access_key=config.MINIO_ACCESS_KEY,
            secret_key=config.MINIO_SECRET_KEY,
            secure=config.MINIO_SECURE
        )
        self._ensure_bucket_exists()
    
    def _ensure_bucket_exists(self):
        """Ensure the bucket exists."""
        try:
            if not self.client.bucket_exists(config.MINIO_BUCKET):
                self.client.make_bucket(config.MINIO_BUCKET)
                logger.info(f"Created bucket: {config.MINIO_BUCKET}")
        except S3Error as e:
            logger.error(f"Error ensuring bucket exists: {e}")
            raise
    
    def upload_file(self, file_data: bytes, object_name: str, content_type: str = "application/octet-stream") -> str:
        """Upload a file to object storage.
        
        Args:
            file_data: File data as bytes
            object_name: Object name (path) in storage
            content_type: Content type of the file
            
        Returns:
            Object path
        """
        try:
            file_obj = io.BytesIO(file_data)
            self.client.put_object(
                config.MINIO_BUCKET,
                object_name,
                file_obj,
                length=len(file_data),
                content_type=content_type
            )
            return object_name
        except S3Error as e:
            logger.error(f"Error uploading file {object_name}: {e}")
            raise
    
    def download_file(self, object_name: str) -> bytes:
        """Download a file from object storage.
        
        Args:
            object_name: Object name (path) in storage
            
        Returns:
            File data as bytes
        """
        try:
            response = self.client.get_object(config.MINIO_BUCKET, object_name)
            return response.read()
        except S3Error as e:
            logger.error(f"Error downloading file {object_name}: {e}")
            raise
        finally:
            response.close()
            response.release_conn()
    
    def delete_file(self, object_name: str):
        """Delete a file from object storage.
        
        Args:
            object_name: Object name (path) in storage
        """
        try:
            self.client.remove_object(config.MINIO_BUCKET, object_name)
        except S3Error as e:
            logger.error(f"Error deleting file {object_name}: {e}")
            raise
    
    def file_exists(self, object_name: str) -> bool:
        """Check if a file exists in object storage.
        
        Args:
            object_name: Object name (path) in storage
            
        Returns:
            True if file exists, False otherwise
        """
        try:
            self.client.stat_object(config.MINIO_BUCKET, object_name)
            return True
        except S3Error:
            return False
