"""Authentication service."""
import hashlib
import psycopg2
from psycopg2.extras import RealDictCursor
from typing import Optional
from uuid import UUID
from shared.config import config
import logging
import json
import time

logger = logging.getLogger(__name__)

# #region agent log
DEBUG_LOG_PATH = "/app/shared/debug.log"
def _debug_log(hyp_id, loc, msg, data=None):
    try:
        with open(DEBUG_LOG_PATH, "a") as f: f.write(json.dumps({"hypothesisId":hyp_id,"location":loc,"message":msg,"data":data or {},"timestamp":int(time.time()*1000),"sessionId":"debug-session"})+"\n")
    except: pass
# #endregion


class AuthService:
    """Service for authentication and tenant management."""
    
    def __init__(self):
        self.conn = psycopg2.connect(config.DATABASE_URL)
    
    def _hash_api_key(self, api_key: str) -> str:
        """Hash an API key (simple hash for prototype, use bcrypt in production).
        
        Args:
            api_key: API key to hash
            
        Returns:
            Hashed API key
        """
        return hashlib.sha256(api_key.encode()).hexdigest()
    
    def authenticate(self, api_key: str) -> Optional[dict]:
        """Authenticate an API key and return tenant information.
        
        Args:
            api_key: API key to authenticate
            
        Returns:
            Tenant information dict or None if invalid
        """
        # #region agent log
        _debug_log("H1", "auth.py:authenticate:entry", "Auth called", {"api_key_preview": api_key[:10] if api_key else None})
        # #endregion
        try:
            api_key_hash = self._hash_api_key(api_key)
            # #region agent log
            _debug_log("H1", "auth.py:authenticate:hash", "Computed hash", {"hash": api_key_hash})
            # #endregion
            
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT tenant_id, name, rate_limit, created_at
                    FROM tenants
                    WHERE api_key_hash = %s
                    """,
                    (api_key_hash,)
                )
                result = cur.fetchone()
                # #region agent log
                _debug_log("H1", "auth.py:authenticate:result", "DB query result", {"found": result is not None, "tenant_name": result["name"] if result else None})
                # #endregion
                
                if result:
                    return dict(result)
                return None
        except Exception as e:
            # #region agent log
            _debug_log("H1", "auth.py:authenticate:error", "Auth exception", {"error": str(e)})
            # #endregion
            logger.error(f"Error authenticating: {e}")
            return None
    
    def get_tenant(self, tenant_id: UUID) -> Optional[dict]:
        """Get tenant information by ID.
        
        Args:
            tenant_id: Tenant ID
            
        Returns:
            Tenant information dict or None if not found
        """
        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT tenant_id, name, rate_limit, created_at
                    FROM tenants
                    WHERE tenant_id = %s
                    """,
                    (str(tenant_id),)
                )
                result = cur.fetchone()
                
                if result:
                    return dict(result)
                return None
        except Exception as e:
            logger.error(f"Error getting tenant: {e}")
            return None
    
    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()
