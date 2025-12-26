"""
Tests for JavaScript/TypeScript API call detection (Phase 2).

Tests the extraction of HTTP client calls from JavaScript/TypeScript code including:
- fetch() API calls
- axios calls (method-based and config object)
- Angular HttpClient calls
- Vue $http calls
"""
import pytest
from src.parsers.javascript_parser import JavaScriptParser, TypeScriptParser


class TestJavaScriptApiCallDetection:
    """Test JavaScript parser API call detection."""
    
    def test_fetch_api_get_call(self):
        """Test detection of fetch() GET call."""
        parser = JavaScriptParser()
        code = """
        async function loadUsers() {
            const response = await fetch('/api/users');
            return response.json();
        }
        """
        
        result = parser.parse(code, "test.js")
        
        assert len(result.api_calls) == 1
        api_call = result.api_calls[0]
        assert api_call['http_method'] == 'GET'
        assert api_call['url_pattern'] == '/api/users'
        assert api_call['http_client_library'] == 'fetch'
        assert not api_call['is_dynamic_url']
    
    def test_fetch_api_post_call(self):
        """Test detection of fetch() POST call with options."""
        parser = JavaScriptParser()
        code = """
        async function createUser(userData) {
            const response = await fetch('/api/users', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(userData)
            });
            return response.json();
        }
        """
        
        result = parser.parse(code, "test.js")
        
        assert len(result.api_calls) == 1
        api_call = result.api_calls[0]
        assert api_call['http_method'] == 'POST'
        assert api_call['url_pattern'] == '/api/users'
        assert api_call['http_client_library'] == 'fetch'
        assert api_call['context_metadata']['has_options']
    
    def test_axios_get_call(self):
        """Test detection of axios.get() call."""
        parser = JavaScriptParser()
        code = """
        async function getProducts() {
            const response = await axios.get('/api/products');
            return response.data;
        }
        """
        
        result = parser.parse(code, "test.js")
        
        assert len(result.api_calls) == 1
        api_call = result.api_calls[0]
        assert api_call['http_method'] == 'GET'
        assert api_call['url_pattern'] == '/api/products'
        assert api_call['http_client_library'] == 'axios'
    
    def test_axios_post_call(self):
        """Test detection of axios.post() call with data."""
        parser = JavaScriptParser()
        code = """
        async function createOrder(orderData) {
            return axios.post('/api/orders', orderData);
        }
        """
        
        result = parser.parse(code, "test.js")
        
        assert len(result.api_calls) == 1
        api_call = result.api_calls[0]
        assert api_call['http_method'] == 'POST'
        assert api_call['url_pattern'] == '/api/orders'
        assert api_call['http_client_library'] == 'axios'
        assert api_call['context_metadata']['has_data']
    
    def test_dynamic_url_template_literal(self):
        """Test detection of template literal URL (dynamic)."""
        parser = JavaScriptParser()
        code = """
        async function getUser(id) {
            return fetch(`/api/users/${id}`);
        }
        """
        
        result = parser.parse(code, "test.js")
        
        assert len(result.api_calls) == 1
        api_call = result.api_calls[0]
        assert api_call['is_dynamic_url']
        assert '/api/users/{var}' in api_call['url_pattern']
    
    def test_no_api_calls_in_regular_code(self):
        """Test that regular function calls are not detected as API calls."""
        parser = JavaScriptParser()
        code = """
        function processData(items) {
            return items.map(item => item.value);
        }
        """
        
        result = parser.parse(code, "test.js")
        
        # Should not detect any API calls
        assert len(result.api_calls) == 0


class TestTypeScriptApiCallDetection:
    """Test TypeScript parser API call detection."""
    
    def test_typescript_fetch_with_types(self):
        """Test fetch() call in TypeScript with type annotations."""
        parser = TypeScriptParser()
        code = """
        async function loadUsers(): Promise<User[]> {
            const response = await fetch('/api/users');
            const data: User[] = await response.json();
            return data;
        }
        """
        
        result = parser.parse(code, "test.ts")
        
        assert len(result.api_calls) == 1
        api_call = result.api_calls[0]
        assert api_call['http_method'] == 'GET'
        assert api_call['url_pattern'] == '/api/users'
        assert api_call['http_client_library'] == 'fetch'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
