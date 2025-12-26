"""Test enhanced multi-word search functionality."""

import pytest
from unittest.mock import Mock
from src.api.services.search_service import SearchService
from src.database.models import Symbol


class TestEnhancedSearch:
    """Test enhanced search features."""
    
    def test_tokenize_query_simple(self):
        """Test query tokenization with simple words."""
        service = SearchService(Mock())
        
        tokens = service._tokenize_query("consumer notification handler")
        assert tokens == ["consumer", "notification", "handler"]
    
    def test_tokenize_query_with_stopwords(self):
        """Test query tokenization filters stop words."""
        service = SearchService(Mock())
        
        tokens = service._tokenize_query("get the user by id")
        # Should filter out 'the' and 'by'
        assert "the" not in tokens
        assert "by" not in tokens
        assert "get" in tokens
        assert "user" in tokens
        assert "id" in tokens
    
    def test_tokenize_query_camelcase(self):
        """Test query tokenization with camelCase."""
        service = SearchService(Mock())
        
        tokens = service._tokenize_query("getUserById")
        # Treats as single token (camelCase not split)
        assert "getuserbyid" in tokens
    
    def test_calculate_multiword_score_exact_match(self):
        """Test scoring with exact phrase match."""
        service = SearchService(Mock())
        
        symbol = Mock(spec=Symbol)
        symbol.name = "ConsumerNotificationHandler"
        symbol.signature = "class ConsumerNotificationHandler"
        symbol.documentation = "Handles consumer notifications"
        symbol.fully_qualified_name = "app.handlers.ConsumerNotificationHandler"
        
        query = "consumer notification handler"
        tokens = ["consumer", "notification", "handler"]
        
        score = service._calculate_keyword_score_multiword(symbol, query, tokens)
        
        # Should have high score due to multiple token matches
        assert score > 5.0
    
    def test_calculate_multiword_score_partial_match(self):
        """Test scoring with partial token match."""
        service = SearchService(Mock())
        
        symbol = Mock(spec=Symbol)
        symbol.name = "NotificationHandler"
        symbol.signature = "class NotificationHandler"
        symbol.documentation = "Base notification handler"
        symbol.fully_qualified_name = "app.handlers.NotificationHandler"
        
        query = "consumer notification handler"
        tokens = ["consumer", "notification", "handler"]
        
        score = service._calculate_keyword_score_multiword(symbol, query, tokens)
        
        # Should have moderate score (2 out of 3 tokens match)
        assert score > 2.0
        assert score < 10.0
    
    def test_calculate_multiword_score_single_token(self):
        """Test scoring with single token match."""
        service = SearchService(Mock())
        
        symbol = Mock(spec=Symbol)
        symbol.name = "Consumer"
        symbol.signature = "class Consumer"
        symbol.documentation = "Base consumer class"
        symbol.fully_qualified_name = "app.models.Consumer"
        
        query = "consumer notification handler"
        tokens = ["consumer", "notification", "handler"]
        
        score = service._calculate_keyword_score_multiword(symbol, query, tokens)
        
        # Should have low score (only 1 out of 3 tokens match)
        assert score > 0.0
        assert score < 5.0
    
    def test_calculate_multiword_score_no_match(self):
        """Test scoring with no matches."""
        service = SearchService(Mock())
        
        symbol = Mock(spec=Symbol)
        symbol.name = "DatabaseConnection"
        symbol.signature = "class DatabaseConnection"
        symbol.documentation = "Database connection handler"
        symbol.fully_qualified_name = "app.db.DatabaseConnection"
        
        query = "consumer notification handler"
        tokens = ["consumer", "notification", "handler"]
        
        score = service._calculate_keyword_score_multiword(symbol, query, tokens)
        
        # Should have low or zero score
        assert score < 3.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

