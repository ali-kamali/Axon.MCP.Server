import pytest
from src.parsers.csharp_parser import CSharpParser
from src.config.enums import SymbolKindEnum

@pytest.fixture
def parser():
    return CSharpParser()

def test_routing_integration(parser):
    code = """
    using Microsoft.AspNetCore.Mvc;
    
    namespace MyApi.Controllers
    {
        [ApiController]
        [Route("api/[controller]")]
        public class UsersController : ControllerBase
        {
            [HttpGet("{id}")]
            public IActionResult GetUser(int id)
            {
                return Ok();
            }
            
            [HttpPost]
            public void CreateUser(User user) { }
            
            public void NotAnEndpoint() { }
        }
    }
    """
    
    # helper to match string input expected by parser
    symbols = parser.parse(code, "UsersController.cs").symbols
    
    # 1. Verify GetUser endpoint
    get_method = next((s for s in symbols if s.kind == SymbolKindEnum.METHOD and s.name == "GetUser"), None)
    assert get_method is not None
    assert get_method.structured_docs is not None
    assert 'api_endpoint' in get_method.structured_docs
    
    endpoint = get_method.structured_docs['api_endpoint']
    assert endpoint['method'] == 'GET'
    assert endpoint['route'] == 'api/Users/{id}'
    
    # 2. Verify CreateUser endpoint
    post_method = next((s for s in symbols if s.kind == SymbolKindEnum.METHOD and s.name == "CreateUser"), None)
    assert post_method is not None
    assert post_method.structured_docs is not None
    assert 'api_endpoint' in post_method.structured_docs
    
    endpoint = post_method.structured_docs['api_endpoint']
    assert endpoint['method'] == 'POST'
    assert endpoint['route'] == 'api/Users'
    
    # 3. Verify NotAnEndpoint (public method but no attributes, strict mode currently requires attributes)
    # The RoutingAnalyzer logic I implemented: 
    # "if not explicit_verb_found and not action_route: ... logic to return None or check conventions"
    # Currently it returns None if no explicit attributes are found (safe default).
    
    not_endpoint = next((s for s in symbols if s.kind == SymbolKindEnum.METHOD and s.name == "NotAnEndpoint"), None)
    assert not_endpoint is not None
    # structured_docs might exist (xml docs etc) but should not have 'api_endpoint'
    if not_endpoint.structured_docs:
        assert 'api_endpoint' not in not_endpoint.structured_docs
