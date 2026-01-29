"""Search routes."""
from fastapi import APIRouter, Depends, HTTPException, status, Header
from typing import Optional
from shared.models import SearchRequest, SearchResponse, SearchResult
from api.services.auth import AuthService
from api.services.qdrant_client import QdrantService
import openai
from shared.config import config
import logging

logger = logging.getLogger(__name__)

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
    if not config.OPENAI_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="OpenAI API key not configured"
        )
    
    try:
        # Generate embedding for query
        openai_client = openai.OpenAI(api_key=config.OPENAI_API_KEY)
        response = openai_client.embeddings.create(
            model=config.OPENAI_EMBEDDING_MODEL,
            input=request.query
        )
        query_vector = response.data[0].embedding
        
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
