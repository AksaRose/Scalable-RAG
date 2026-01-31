"""Pytest configuration and fixtures."""
import pytest
import os

# Set test environment variables
os.environ["DATABASE_URL"] = "postgresql://test:test@localhost:5432/test_db"
os.environ["QDRANT_URL"] = "http://localhost:6333"
os.environ["REDIS_URL"] = "redis://localhost:6379/0"
os.environ["EMBEDDING_MODEL"] = "BAAI/bge-small-en-v1.5"
