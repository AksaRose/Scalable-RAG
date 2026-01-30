"""Search routes."""
from fastapi import APIRouter, Depends, HTTPException, status, Header
from typing import Optional
from shared.models import SearchRequest, SearchResponse, SearchResult
from services.auth import AuthService
from services.qdrant_client import QdrantService
from sentence_transformers import SentenceTransformer
from shared.config import config
import logging

logger = logging.getLogger(__name__)

# Load embedding model once at startup
_embedding_model = None

def get_embedding_model():
    """Get or initialize the embedding model."""
    global _embedding_model
    if _embedding_model is None:
        logger.info(f"Loading embedding model: {config.EMBEDDING_MODEL}")
        _embedding_model = SentenceTransformer(config.EMBEDDING_MODEL)
        logger.info("Embedding model loaded successfully")
    return _embedding_model

router = APIRouter(prefix="/search", tags=["search"])

# Dependency for getting current tenant
def get_current_tenant(x_api_key: Optional[str] = Header(None, alias="X-API-Key")) -> dict:
    """Get current tenant from API key."""
    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key required"
        )
    
    auth_service = AuthService()
    tenant = auth_service.authenticate(x_api_key)
    auth_service.close()
    
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key"
        )
    
    return tenant


@router.post("", response_model=SearchResponse)
async def search_documents(
    request: SearchRequest,
    tenant: dict = Depends(get_current_tenant)
):
    """Search documents using semantic search."""
    try:
        # Generate embedding for query using open-source model
        embedding_model = get_embedding_model()
        query_vector = embedding_model.encode(
            request.query,
            show_progress_bar=False,
            convert_to_numpy=True
        ).tolist()
        
        # Search in Qdrant
        qdrant_service = QdrantService()
        search_results = qdrant_service.search(
            query_vector=query_vector,
            tenant_id=str(tenant['tenant_id']),
            limit=request.limit,
            score_threshold=request.score_threshold
        )
        
        # Format results
        results = []
        for result in search_results:
            payload = result.get('payload', {})
            results.append(
                SearchResult(
                    chunk_id=result['id'],
                    document_id=payload.get('document_id'),
                    tenant_id=payload.get('tenant_id'),  # Added: Source tenant reference
                    filename=payload.get('filename', 'Unknown'),
                    text=payload.get('text', ''),
                    score=result['score'],
                    metadata=payload.get('metadata')
                )
            )
        
        return SearchResponse(
            results=results,
            total=len(results),
            query=request.query
        )
    except Exception as e:
        logger.error(f"Error searching: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error searching: {str(e)}"
        )
