"""Queue utilities for job processing."""
import json
import redis
from typing import Optional, Dict, Any
from shared.config import config


class QueueClient:
    """Redis queue client for job management."""
    
    def __init__(self):
        self.redis_client = redis.from_url(config.REDIS_URL, decode_responses=True)
    
    def enqueue_job(
        self,
        job_type: str,
        tenant_id: str,
        document_id: str,
        payload: Dict[str, Any],
        priority: int = 0
    ) -> str:
        """Enqueue a job to the appropriate tenant queue.
        
        Args:
            job_type: Type of job (extract, chunk, embed)
            tenant_id: Tenant ID
            document_id: Document ID
            payload: Job payload
            priority: Job priority (higher = more priority)
            
        Returns:
            Job ID
        """
        job_data = {
            "job_type": job_type,
            "tenant_id": tenant_id,
            "document_id": document_id,
            "payload": payload,
            "priority": priority
        }
        
        # Use tenant-specific queue for fairness
        queue_name = f"queue:{tenant_id}:{job_type}"
        
        # Add to sorted set for priority-based processing
        job_id = f"{tenant_id}:{document_id}:{job_type}"
        score = priority  # Higher priority = higher score
        
        self.redis_client.zadd(
            queue_name,
            {json.dumps(job_data): score}
        )
        
        return job_id
    
    def dequeue_job(self, job_type: str, tenant_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Dequeue a job from the queue.
        
        Args:
            job_type: Type of job to dequeue
            tenant_id: Optional tenant ID to dequeue from specific tenant
            
        Returns:
            Job data or None if no jobs available
        """
        if tenant_id:
            # Dequeue from specific tenant queue
            queue_name = f"queue:{tenant_id}:{job_type}"
            result = self.redis_client.zpopmax(queue_name, count=1)
            if result:
                return json.loads(result[0][0])
        else:
            # Round-robin across all tenant queues for fairness
            # Get all tenant queues for this job type
            pattern = f"queue:*:{job_type}"
            queues = self.redis_client.keys(pattern)
            
            if not queues:
                return None
            
            # Try each queue in round-robin fashion
            for queue_name in queues:
                result = self.redis_client.zpopmax(queue_name, count=1)
                if result:
                    return json.loads(result[0][0])
        
        return None
    
    def get_queue_size(self, job_type: str, tenant_id: Optional[str] = None) -> int:
        """Get the size of a queue.
        
        Args:
            job_type: Type of job
            tenant_id: Optional tenant ID
            
        Returns:
            Queue size
        """
        if tenant_id:
            queue_name = f"queue:{tenant_id}:{job_type}"
            return self.redis_client.zcard(queue_name)
        else:
            pattern = f"queue:*:{job_type}"
            queues = self.redis_client.keys(pattern)
            total = 0
            for queue_name in queues:
                total += self.redis_client.zcard(queue_name)
            return total
    
    def clear_queue(self, job_type: str, tenant_id: Optional[str] = None):
        """Clear a queue.
        
        Args:
            job_type: Type of job
            tenant_id: Optional tenant ID
        """
        if tenant_id:
            queue_name = f"queue:{tenant_id}:{job_type}"
            self.redis_client.delete(queue_name)
        else:
            pattern = f"queue:*:{job_type}"
            queues = self.redis_client.keys(pattern)
            if queues:
                self.redis_client.delete(*queues)
