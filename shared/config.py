"""Shared configuration for the application."""
import os
from typing import Optional

class Config:
    """Application configuration."""
    
    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql://rag_user:rag_password@localhost:5432/rag_db")
    
    # Qdrant
    QDRANT_URL: str = os.getenv("QDRANT_URL", "http://localhost:6333")
    QDRANT_COLLECTION_NAME: str = "document_chunks"
    QDRANT_VECTOR_SIZE: int = 384  # BAAI/bge-small-en-v1.5
    
    # Redis
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    
    # MinIO/S3
    MINIO_ENDPOINT: str = os.getenv("MINIO_ENDPOINT", "localhost:9000")
    MINIO_ACCESS_KEY: str = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
    MINIO_SECRET_KEY: str = os.getenv("MINIO_SECRET_KEY", "minioadmin")
    MINIO_BUCKET: str = os.getenv("MINIO_BUCKET", "documents")
    MINIO_SECURE: bool = os.getenv("MINIO_SECURE", "false").lower() == "true"
    
    # Embedding Model (Open-source)
    EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5")
    EMBEDDING_BATCH_SIZE: int = 100
    
    # Chunking
    CHUNK_SIZE: int = 512  # tokens
    CHUNK_OVERLAP: int = 50  # tokens (10-20% overlap)
    
    # Processing
    MAX_RETRIES: int = 3
    RETRY_BACKOFF_BASE: float = 2.0
    
    # Rate Limiting
    DEFAULT_RATE_LIMIT: int = 100  # requests per minute
    
    # File Upload
    MAX_FILE_SIZE: int = 100 * 1024 * 1024  # 100MB
    ALLOWED_EXTENSIONS: set = {".pdf", ".txt"}

config = Config()
