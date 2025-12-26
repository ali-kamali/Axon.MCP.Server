"""Unit tests for LinkService (Phase 3: The Linker)."""

import pytest
import warnings
from unittest.mock import AsyncMock, MagicMock, patch
from src.services.link_service import LinkService


class TestLinkService:
    """Tests for LinkService URL matching and gateway resolution."""
    
    def test_normalize_url_pattern_basic(self):
        """Test URL pattern normalization."""
        service = LinkService(MagicMock())
        
        # Basic paths
        assert service._normalize_url_pattern("/api/users") == "api/users"
        assert service._normalize_url_pattern("/api/users/") == "api/users"
        assert service._normalize_url_pattern("api/users") == "api/users"
    
    def test_normalize_url_pattern_with_parameters(self):
        """Test URL pattern normalization with path parameters."""
        service = LinkService(MagicMock())
        
        # Path parameters in different formats
        assert service._normalize_url_pattern("/api/users/{id}") == "api/users/*"
        assert service._normalize_url_pattern("/api/users/:id") == "api/users/*"
        assert service._normalize_url_pattern("/api/users/123") == "api/users/*"
        
        # Multiple parameters
        assert service._normalize_url_pattern("/api/users/{userId}/orders/{orderId}") == "api/users/*/orders/*"
    
    def test_exact_match(self):
        """Test exact URL matching."""
        service = LinkService(MagicMock())
        
        # Exact matches
        assert service._exact_match("/api/users", "/api/users") is True
        assert service._exact_match("/api/users/{id}", "/api/users/:userId") is True
        
        # Non-matches
        assert service._exact_match("/api/users", "/api/orders") is False
    
    def test_path_similarity(self):
        """Test URL path similarity scoring."""
        service = LinkService(MagicMock())
        
        # High similarity
        similarity = service._path_similarity("/api/users/list", "/api/users/all")
        assert similarity > 0.7
        
        # Low similarity
        similarity = service._path_similarity("/api/users", "/api/completely/different")
        assert similarity < 0.5
    
    def test_http_method_matches_exact(self):
        """Test HTTP method matching with exact match."""
        service = LinkService(MagicMock())
        
        # Create mock symbol with structured_docs
        symbol = MagicMock()
        symbol.structured_docs = {"http_method": "GET"}
        symbol.name = "GetUsers"
        symbol.signature = "GET /api/users"
        
        assert service._http_method_matches("GET", symbol) is True
        assert service._http_method_matches("POST", symbol) is False
    
    def test_http_method_matches_by_name_pattern(self):
        """Test HTTP method matching by method name patterns."""
        service = LinkService(MagicMock())
        
        # Mock symbol without explicit http_method
        symbol = MagicMock()
        symbol.structured_docs = {}
        symbol.signature = None
        
        # GET patterns
        symbol.name = "GetAllUsers"
        assert service._http_method_matches("GET", symbol) is True
        
        symbol.name = "FetchUserById"
        assert service._http_method_matches("GET", symbol) is True
        
        # POST patterns
        symbol.name = "CreateNewUser"
        assert service._http_method_matches("POST", symbol) is True
        
        # DELETE patterns
        symbol.name = "RemoveUser"
        assert service._http_method_matches("DELETE", symbol) is True
    
    def test_extract_route_from_symbol_structured_docs(self):
        """Test route extraction from symbol structured_docs."""
        service = LinkService(MagicMock())
        
        # API endpoint type
        symbol = MagicMock()
        symbol.structured_docs = {"type": "api_endpoint", "route": "/api/users"}
        symbol.attributes = None
        symbol.signature = None
        symbol.documentation = None
        
        assert service._extract_route_from_symbol(symbol) == "/api/users"
    
    def test_extract_route_from_symbol_attributes(self):
        """Test route extraction from symbol attributes."""
        service = LinkService(MagicMock())
        
        symbol = MagicMock()
        symbol.structured_docs = {
            "attributes": [
                {"name": "Route", "arguments": ['"api/users"']}
            ]
        }
        symbol.attributes = None
        symbol.signature = None
        symbol.documentation = None
        
        assert service._extract_route_from_symbol(symbol) == "api/users"
    
    def test_extract_route_from_symbol_signature(self):
        """Test route extraction from symbol signature."""
        service = LinkService(MagicMock())
        
        symbol = MagicMock()
        symbol.structured_docs = None
        symbol.attributes = None
        symbol.signature = "GET /api/users/{id}"
        symbol.documentation = None
        
        assert service._extract_route_from_symbol(symbol) == "/api/users/{id}"
    
    def test_routing_key_matches_exact(self):
        """Test RabbitMQ routing key matching - exact match."""
        service = LinkService(MagicMock())
        
        assert service._routing_key_matches("user.created", "user.created") is True
        assert service._routing_key_matches("user.created", "user.deleted") is False
    
    def test_routing_key_matches_wildcard(self):
        """Test RabbitMQ routing key matching - single word wildcard."""
        service = LinkService(MagicMock())
        
        # * matches exactly one word
        assert service._routing_key_matches("user.created", "user.*") is True
        assert service._routing_key_matches("user.created.event", "user.*") is False
    
    def test_routing_key_matches_hash_wildcard(self):
        """Test RabbitMQ routing key matching - multi-word wildcard."""
        service = LinkService(MagicMock())
        
        # # matches zero or more words
        assert service._routing_key_matches("user.created", "user.#") is True
        assert service._routing_key_matches("user.created.event", "user.#") is True
        assert service._routing_key_matches("user", "user.#") is True


class TestGatewayResolution:
    """Tests for gateway route resolution."""
    
    def test_resolve_through_gateway_empty_routes(self):
        """Test resolution with no gateway routes."""
        service = LinkService(MagicMock())
        
        resolved, metadata = service._resolve_through_gateway("/api/users", [])
        
        assert resolved is None
        assert metadata == {}
    
    def test_resolve_through_gateway_ocelot(self):
        """Test resolution through Ocelot gateway."""
        service = LinkService(MagicMock())
        
        # Create mock Ocelot route
        route = MagicMock()
        route.downstream_path_template = "/api/users/{id}"
        route.upstream_path_template = "/users/{id}"
        route.gateway_type = "ocelot"
        route.id = 1
        route.upstream_host = "user-service"
        route.upstream_port = 8080
        route.route_name = "user-route"
        route.priority = 1
        route.route_metadata = {}
        
        # Mock the Ocelot parser
        service.ocelot_parser.resolve_path_through_route = MagicMock(return_value="/users/123")
        
        resolved, metadata = service._resolve_through_gateway("/api/users/123", [route])
        
        assert resolved == "/users/123"
        assert metadata["gateway_type"] == "ocelot"
        assert metadata["gateway_route_id"] == 1
        assert metadata["upstream_host"] == "user-service"


class TestDeprecationWarnings:
    """Tests for deprecated sync methods."""
    
    def test_find_matching_endpoint_deprecation_warning(self):
        """Test that sync wrapper emits deprecation warning."""
        service = LinkService(MagicMock())
        
        call = MagicMock()
        call.url_pattern = "/api/users"
        call.http_method = "GET"
        
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            # Call sync method - should emit warning
            service.find_matching_endpoint(call, [])
            
            assert len(w) >= 1
            assert issubclass(w[0].category, DeprecationWarning)
            assert "deprecated" in str(w[0].message).lower()
    
    def test_find_candidate_endpoints_deprecation_warning(self):
        """Test that sync wrapper emits deprecation warning."""
        service = LinkService(MagicMock())
        
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            service._find_candidate_endpoints("/api/users", "GET")
            
            assert len(w) >= 1
            assert issubclass(w[0].category, DeprecationWarning)


class TestOcelotParserFixes:
    """Tests for fixed Ocelot parser."""
    
    def test_ocelot_resolve_standard_placeholder(self):
        """Test standard placeholder resolution."""
        from src.parsers.ocelot_parser import OcelotParser
        parser = OcelotParser()
        
        route = {
            'downstream_path': '/api/users/{id}',
            'upstream_path': '/users/{id}'
        }
        
        result = parser.resolve_path_through_route('/api/users/123', route)
        assert result == '/users/123'
    
    def test_ocelot_resolve_catch_all_everything(self):
        """Test {everything} catch-all placeholder."""
        from src.parsers.ocelot_parser import OcelotParser
        parser = OcelotParser()
        
        route = {
            'downstream_path': '/api/{everything}',
            'upstream_path': '/{everything}'
        }
        
        result = parser.resolve_path_through_route('/api/users/123/orders', route)
        assert result == '/users/123/orders'
    
    def test_ocelot_resolve_catch_all_url(self):
        """Test {url} catch-all placeholder."""
        from src.parsers.ocelot_parser import OcelotParser
        parser = OcelotParser()
        
        route = {
            'downstream_path': '/gateway/{url}',
            'upstream_path': '/backend/{url}'
        }
        
        result = parser.resolve_path_through_route('/gateway/v1/api/users', route)
        assert result == '/backend/v1/api/users'
    
    def test_ocelot_resolve_multiple_placeholders(self):
        """Test multiple placeholders in same route."""
        from src.parsers.ocelot_parser import OcelotParser
        parser = OcelotParser()
        
        route = {
            'downstream_path': '/api/users/{userId}/orders/{orderId}',
            'upstream_path': '/orders/{orderId}/user/{userId}'
        }
        
        result = parser.resolve_path_through_route('/api/users/42/orders/99', route)
        assert result == '/orders/99/user/42'
    
    def test_ocelot_resolve_no_match(self):
        """Test non-matching path returns None."""
        from src.parsers.ocelot_parser import OcelotParser
        parser = OcelotParser()
        
        route = {
            'downstream_path': '/api/users/{id}',
            'upstream_path': '/users/{id}'
        }
        
        result = parser.resolve_path_through_route('/api/orders/123', route)
        assert result is None


class TestNginxParserFixes:
    """Tests for fixed Nginx parser."""
    
    def test_nginx_resolve_prefix_location(self):
        """Test prefix location resolution."""
        from src.parsers.nginx_parser import NginxParser
        parser = NginxParser()
        
        route = {
            'downstream_path': '/api/',
            'upstream_path': '/backend/',
            'is_regex': False
        }
        
        result = parser.resolve_path_through_route('/api/users/123', route)
        assert result == '/backend/users/123'
    
    def test_nginx_resolve_regex_with_groups(self):
        """Test regex location with capture groups."""
        from src.parsers.nginx_parser import NginxParser
        parser = NginxParser()
        
        route = {
            'downstream_path': r'^/api/v(\d+)/(.+)$',
            'upstream_path': '/backend/$2?version=$1',
            'is_regex': True
        }
        
        result = parser.resolve_path_through_route('/api/v2/users/123', route)
        assert result == '/backend/users/123?version=2'
    
    def test_nginx_resolve_regex_reverse_order(self):
        """Test that $12 is not affected by $1 replacement."""
        from src.parsers.nginx_parser import NginxParser
        parser = NginxParser()
        
        # Create route with 12+ capture groups
        route = {
            'downstream_path': r'^/(.)/(.)/(.)/(.)/(.)/(.)/(.)/(.)/(.)/(.)/(.)/(.+)$',
            'upstream_path': '/out/$12/$1',
            'is_regex': True
        }
        
        result = parser.resolve_path_through_route('/a/b/c/d/e/f/g/h/i/j/k/final', route)
        # $12 should be "final", $1 should be "a"
        assert result == '/out/final/a'


class TestCalculateMatchScore:
    """Tests for match score calculation."""
    
    def test_calculate_match_score_exact_match(self):
        """Test score calculation for exact URL match."""
        service = LinkService(MagicMock())
        
        call = MagicMock()
        call.url_pattern = "/api/users"
        call.http_method = "GET"
        
        endpoint = MagicMock()
        endpoint.structured_docs = {"type": "api_endpoint", "route": "/api/users", "http_method": "GET"}
        endpoint.attributes = None
        endpoint.signature = None
        endpoint.documentation = None
        endpoint.name = "GetUsers"
        
        score, metadata = service._calculate_match_score(call, endpoint, None)
        
        # Should have high score: 0.5 (URL) + 0.3 (method) + 0.1 (base) = 0.9
        assert score >= 0.8
        assert metadata["url_match"] == "exact"
        assert metadata["method_match"] is True
    
    def test_calculate_match_score_gateway_resolved(self):
        """Test score calculation with gateway resolution bonus."""
        service = LinkService(MagicMock())
        
        call = MagicMock()
        call.url_pattern = "/api/users"
        call.http_method = "GET"
        
        endpoint = MagicMock()
        endpoint.structured_docs = {"type": "api_endpoint", "route": "/users", "http_method": "GET"}
        endpoint.attributes = None
        endpoint.signature = None
        endpoint.documentation = None
        endpoint.name = "GetUsers"
        
        # Passing resolved_url adds gateway bonus
        score, metadata = service._calculate_match_score(call, endpoint, "/users")
        
        # Should have full score with gateway: 0.5 (URL) + 0.3 (method) + 0.2 (gateway) = 1.0
        assert score >= 0.9
        assert metadata["gateway_resolved"] is True

