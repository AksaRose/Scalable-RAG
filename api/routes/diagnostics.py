"""Diagnostics endpoint for checking system health."""
from fastapi import APIRouter
from shared.config import config
import psycopg2
from minio import Minio
import redis
from qdrant_client import QdrantClient
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/diagnostics", tags=["diagnostics"])


@router.get("/")
async def check_all_connections():
    """Check all system connections."""
    results = {
        "database": {"status": "unknown", "error": None},
        "redis": {"status": "unknown", "error": None},
        "minio": {"status": "unknown", "error": None},
        "qdrant": {"status": "unknown", "error": None},
    }
    
    # Check database
    try:
        conn = psycopg2.connect(config.DATABASE_URL)
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
        conn.close()
        results["database"]["status"] = "connected"
    except Exception as e:
        results["database"]["status"] = "failed"
        results["database"]["error"] = str(e)
    
    # Check Redis
    try:
        r = redis.from_url(config.REDIS_URL)
        r.ping()
        results["redis"]["status"] = "connected"
    except Exception as e:
        results["redis"]["status"] = "failed"
        results["redis"]["error"] = str(e)
    
    # Check MinIO
    try:
        client = Minio(
            config.MINIO_ENDPOINT,
            access_key=config.MINIO_ACCESS_KEY,
            secret_key=config.MINIO_SECRET_KEY,
            secure=config.MINIO_SECURE
        )
        client.list_buckets()
        results["minio"]["status"] = "connected"
    except Exception as e:
        results["minio"]["status"] = "failed"
        results["minio"]["error"] = str(e)
    
    # Check Qdrant
    try:
        client = QdrantClient(url=config.QDRANT_URL)
        client.get_collections()
        results["qdrant"]["status"] = "connected"
    except Exception as e:
        results["qdrant"]["status"] = "failed"
        results["qdrant"]["error"] = str(e)
    
    all_healthy = all(r["status"] == "connected" for r in results.values())
    
    return {
        "status": "healthy" if all_healthy else "unhealthy",
        "connections": results
    }
