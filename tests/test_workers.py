"""Unit tests for workers."""
import pytest
from unittest.mock import Mock, patch, MagicMock
import uuid
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))


class TestTextExtractor:
    """Tests for text extractor worker."""
    
    @patch('workers.text_extractor.worker.StorageService')
    @patch('workers.text_extractor.worker.QueueClient')
    @patch('workers.text_extractor.worker.psycopg2.connect')
    def test_extract_text_from_pdf(self, mock_db, mock_queue, mock_storage):
        """Test PDF text extraction."""
        from workers.text_extractor.worker import TextExtractorWorker
        
        worker = TextExtractorWorker()
        
        # Mock PDF content
        mock_pdf_content = b"fake pdf content"
        
        # Test extraction (will fail without actual PDF, but tests structure)
        with patch('workers.text_extractor.worker.PdfReader') as mock_pdf:
            mock_reader = Mock()
            mock_page = Mock()
            mock_page.extract_text.return_value = "Extracted text"
            mock_reader.pages = [mock_page]
            mock_pdf.return_value = mock_reader
            
            result = worker.extract_text_from_pdf(mock_pdf_content)
            assert "Extracted text" in result
    
    @patch('workers.text_extractor.worker.StorageService')
    @patch('workers.text_extractor.worker.QueueClient')
    @patch('workers.text_extractor.worker.psycopg2.connect')
    def test_extract_text_from_txt(self, mock_db, mock_queue, mock_storage):
        """Test TXT text extraction."""
        from workers.text_extractor.worker import TextExtractorWorker
        
        worker = TextExtractorWorker()
        
        # Test TXT extraction
        txt_content = b"Hello, World!"
        result = worker.extract_text_from_txt(txt_content)
        assert result == "Hello, World!"


class TestChunker:
    """Tests for chunker worker."""
    
    @patch('workers.chunker.worker.StorageService')
    @patch('workers.chunker.worker.QueueClient')
    @patch('workers.chunker.worker.psycopg2.connect')
    def test_chunk_text(self, mock_db, mock_queue, mock_storage):
        """Test text chunking."""
        from workers.chunker.worker import ChunkerWorker
        
        worker = ChunkerWorker()
        
        # Test chunking
        text = "This is a test. " * 100  # Long text
        chunks = worker.chunk_text(text, chunk_size=100, overlap=20)
        
        assert len(chunks) > 0
        assert all('text' in chunk for chunk in chunks)
        assert all('chunk_index' in chunk for chunk in chunks)


class TestEmbedder:
    """Tests for embedder worker."""
    
    @patch('workers.embedder.worker.StorageService')
    @patch('workers.embedder.worker.QdrantService')
    @patch('workers.embedder.worker.QueueClient')
    @patch('workers.embedder.worker.psycopg2.connect')
    @patch('workers.embedder.worker.SentenceTransformer')
    def test_generate_embeddings(self, mock_sentence_transformer, mock_db, mock_queue, mock_qdrant, mock_storage):
        """Test embedding generation."""
        from workers.embedder.worker import EmbedderWorker
        
        # Mock SentenceTransformer
        mock_model_instance = Mock()
        mock_model_instance.encode.return_value = [[0.1] * 384]  # 384 dimensions for bge-small
        mock_sentence_transformer.return_value = mock_model_instance
        
        worker = EmbedderWorker()
        
        texts = ["Test text"]
        embeddings = worker.generate_embeddings(texts)
        
        assert len(embeddings) == 1
        assert len(embeddings[0]) == 384
