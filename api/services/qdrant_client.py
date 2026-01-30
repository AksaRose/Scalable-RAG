"""Qdrant client service."""
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct, Filter, FieldCondition, MatchValue
from typing import List, Dict, Any, Optional
from shared.config import config
import logging

logger = logging.getLogger(__name__)


class QdrantService:
    """Service for interacting with Qdrant vector database."""
    
    def __init__(self):
        self.client = QdrantClient(url=config.QDRANT_URL)
        self.collection_name = config.QDRANT_COLLECTION_NAME
        self._ensure_collection_exists()
    
    def _ensure_collection_exists(self):
        """Ensure the collection exists with proper indexes."""
        try:
            collections = self.client.get_collections().collections
            collection_names = [c.name for c in collections]
            
            if self.collection_name not in collection_names:
                self.client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=VectorParams(
                        size=config.QDRANT_VECTOR_SIZE,
                        distance=Distance.COSINE
                    )
                )
                logger.info(f"Created collection: {self.collection_name}")
                
                # Create payload index on tenant_id for fast filtering at scale
                self.client.create_payload_index(
                    collection_name=self.collection_name,
                    field_name="tenant_id",
                    field_schema="keyword"
                )
                logger.info(f"Created payload index on tenant_id")
        except Exception as e:
            logger.error(f"Error ensuring collection exists: {e}")
            raise
    
    def upsert_points(
        self,
        points: List[Dict[str, Any]],
        tenant_id: str
    ):
        """Upsert points (vectors) to Qdrant.
        
        Args:
            points: List of point dictionaries with 'id', 'vector', 'payload'
            tenant_id: Tenant ID for filtering
        """
        try:
            point_structs = []
            for point in points:
                # Ensure tenant_id is in payload
                payload = point.get('payload', {})
                payload['tenant_id'] = tenant_id
                
                point_structs.append(
                    PointStruct(
                        id=point['id'],
                        vector=point['vector'],
                        payload=payload
                    )
                )
            
            self.client.upsert(
                collection_name=self.collection_name,
                points=point_structs
            )
            logger.info(f"Upserted {len(point_structs)} points for tenant {tenant_id}")
        except Exception as e:
            logger.error(f"Error upserting points: {e}")
            raise
    
    def search(
        self,
        query_vector: List[float],
        tenant_id: str,
        limit: int = 10,
        score_threshold: float = 0.7
    ) -> List[Dict[str, Any]]:
        """Search for similar vectors.
        
        Args:
            query_vector: Query embedding vector
            tenant_id: Tenant ID for filtering
            limit: Maximum number of results
            score_threshold: Minimum similarity score
            
        Returns:
            List of search results
        """
        try:
            # Create filter for tenant isolation
            filter_condition = Filter(
                must=[
                    FieldCondition(
                        key="tenant_id",
                        match=MatchValue(value=tenant_id)
                    )
                ]
            )
            
            search_results = self.client.search(
                collection_name=self.collection_name,
                query_vector=query_vector,
                query_filter=filter_condition,
                limit=limit,
                score_threshold=score_threshold
            )
            
            results = []
            for result in search_results:
                results.append({
                    'id': result.id,
                    'score': result.score,
                    'payload': result.payload
                })
            
            return results
        except Exception as e:
            logger.error(f"Error searching: {e}")
            raise
    
    def delete_points(
        self,
        point_ids: List[str],
        tenant_id: Optional[str] = None
    ):
        """Delete points from Qdrant.
        
        Args:
            point_ids: List of point IDs to delete
            tenant_id: Optional tenant ID for additional filtering
        """
        try:
            filter_condition = None
            if tenant_id:
                filter_condition = Filter(
                    must=[
                        FieldCondition(
                            key="tenant_id",
                            match=MatchValue(value=tenant_id)
                        )
                    ]
                )
            
            self.client.delete(
                collection_name=self.collection_name,
                points_selector=point_ids,
                query_filter=filter_condition
            )
            logger.info(f"Deleted {len(point_ids)} points")
        except Exception as e:
            logger.error(f"Error deleting points: {e}")
            raise
