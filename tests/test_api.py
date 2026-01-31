"""Unit tests for API endpoints."""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch, MagicMock
import uuid
from api.main import app

client = TestClient(app)


@pytest.fixture
def mock_tenant():
    """Mock tenant data."""
    return {
        'tenant_id': str(uuid.uuid4()),
        'name': 'test_tenant',
        'rate_limit': 100,
        'created_at': '2024-01-01T00:00:00'
    }


@pytest.fixture
def mock_auth_service(mock_tenant):
    """Mock auth service."""
    with patch('api.routes.upload.AuthService') as mock_auth:
        mock_instance = Mock()
        mock_instance.authenticate.return_value = mock_tenant
        mock_instance.close.return_value = None
        mock_auth.return_value = mock_instance
        yield mock_instance


class TestUpload:
    """Tests for upload endpoints."""
    
    @patch('api.routes.upload.StorageService')
    @patch('api.routes.upload.QueueClient')
    @patch('api.routes.upload.psycopg2.connect')
    def test_upload_single_file_success(self, mock_db, mock_queue, mock_storage, mock_auth_service, mock_tenant):
        """Test successful single file upload."""
        # Mock database
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = {
            'document_id': str(uuid.uuid4()),
            'status': 'pending'
        }
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_db.return_value = mock_conn
        
        # Mock storage
        mock_storage_instance = Mock()
        mock_storage.return_value = mock_storage_instance
        
        # Mock queue
        mock_queue_instance = Mock()
        mock_queue.return_value = mock_queue_instance
        
        # Create test file
        test_file = ("test.pdf", b"fake pdf content", "application/pdf")
        
        response = client.post(
            "/upload/single",
            headers={"X-API-Key": "test_api_key_123"},
            files={"file": test_file}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "document_id" in data
        assert data["status"] == "pending"
        assert data["filename"] == "test.pdf"
    
    def test_upload_single_file_no_api_key(self):
        """Test upload without API key."""
        test_file = ("test.pdf", b"fake pdf content", "application/pdf")
        
        response = client.post(
            "/upload/single",
            files={"file": test_file}
        )
        
        assert response.status_code == 401
    
    def test_upload_single_file_invalid_extension(self, mock_auth_service, mock_tenant):
        """Test upload with invalid file extension."""
        test_file = ("test.exe", b"fake content", "application/octet-stream")
        
        response = client.post(
            "/upload/single",
            headers={"X-API-Key": "test_api_key_123"},
            files={"file": test_file}
        )
        
        assert response.status_code == 400
        assert "not allowed" in response.json()["detail"].lower()


class TestSearch:
    """Tests for search endpoints."""
    
    @patch('api.routes.search.SentenceTransformer')
    @patch('api.routes.search.QdrantService')
    def test_search_success(self, mock_qdrant, mock_sentence_transformer, mock_auth_service, mock_tenant):
        """Test successful search."""
        # Mock SentenceTransformer
        mock_model_instance = Mock()
        mock_model_instance.encode.return_value = [[0.1] * 384]  # 384 dimensions for bge-small
        mock_sentence_transformer.return_value = mock_model_instance
        
        # Mock Qdrant
        mock_qdrant_instance = Mock()
        mock_qdrant_instance.search.return_value = [
            {
                'id': str(uuid.uuid4()),
                'score': 0.95,
                'payload': {
                    'document_id': str(uuid.uuid4()),
                    'filename': 'test.pdf',
                    'text': 'Test content',
                    'chunk_index': 0
                }
            }
        ]
        mock_qdrant.return_value = mock_qdrant_instance
        
        response = client.post(
            "/search",
            headers={"X-API-Key": "test_api_key_123"},
            json={
                "query": "test query",
                "limit": 10,
                "score_threshold": 0.7
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "results" in data
        assert len(data["results"]) > 0
        assert data["query"] == "test query"
    
    def test_search_no_api_key(self):
        """Test search without API key."""
        response = client.post(
            "/search",
            json={
                "query": "test query",
                "limit": 10
            }
        )
        
        assert response.status_code == 401


class TestStatus:
    """Tests for status endpoints."""
    
    @patch('api.routes.status.psycopg2.connect')
    def test_get_status_success(self, mock_db, mock_auth_service, mock_tenant):
        """Test successful status retrieval."""
        # Mock database
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        
        # Mock document query
        mock_cursor.fetchone.side_effect = [
            {
                'document_id': str(uuid.uuid4()),
                'status': 'completed',
                'metadata': {}
            },
            []  # No jobs
        ]
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_db.return_value = mock_conn
        
        document_id = uuid.uuid4()
        response = client.get(
            f"/status/{document_id}",
            headers={"X-API-Key": "test_api_key_123"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["document_id"] == str(document_id)
        assert "status" in data
    
    def test_get_status_no_api_key(self):
        """Test status retrieval without API key."""
        document_id = uuid.uuid4()
        response = client.get(
            f"/status/{document_id}"
        )
        
        assert response.status_code == 401


class TestHealth:
    """Tests for health check endpoint."""
    
    def test_health_check(self):
        """Test health check endpoint."""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"
    
    def test_root_endpoint(self):
        """Test root endpoint."""
        response = client.get("/")
        assert response.status_code == 200
        assert "message" in response.json()
