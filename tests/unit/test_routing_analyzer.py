import pytest
import tree_sitter_c_sharp as tscsharp
from tree_sitter import Language, Parser
from src.extractors.routing_analyzer import RoutingAnalyzer

@pytest.fixture
def parser():
    language = Language(tscsharp.language())
    parser = Parser(language)
    return parser

@pytest.fixture
def analyzer():
    return RoutingAnalyzer()

def test_basic_route(parser, analyzer):
    code = """
    [ApiController]
    [Route("api/[controller]")]
    public class UsersController : ControllerBase
    {
        [HttpGet]
        public IEnumerable<User> Get()
        {
            return _users;
        }
    }
    """
    tree = parser.parse(bytes(code, "utf8"))
    class_node = tree.root_node.child(0) # class_declaration (ignoring potential whitespace/comment nodes if any?)
    # Tree-sitter root children might include comments generally, but here likely index 0 or 1.
    # We should search for class_declaration
    
    for child in tree.root_node.children:
        if child.type == 'class_declaration':
            class_node = child
            break
            
    method_node = None
    # find method
    class_body = class_node.child_by_field_name('body')
    for child in class_body.children:
        if child.type == 'method_declaration':
            method_node = child
            break
            
    info = analyzer.analyze(class_node, method_node, code)
    
    assert info is not None
    assert info.http_method == "GET"
    assert info.route_template == "api/Users"

def test_route_with_id(parser, analyzer):
    code = """
    [Route("api/[controller]")]
    public class UsersController
    {
        [HttpGet("{id}")]
        public User Get(int id) { }
    }
    """
    tree = parser.parse(bytes(code, "utf8"))
    
    class_node = next(c for c in tree.root_node.children if c.type == 'class_declaration')
    class_body = class_node.child_by_field_name('body')
    method_node = next(c for c in class_body.children if c.type == 'method_declaration')
    
    info = analyzer.analyze(class_node, method_node, code)
    
    assert info.http_method == "GET"
    assert info.route_template == "api/Users/{id}"

def test_action_override(parser, analyzer):
    # Action route starting with / overrides controller route
    code = """
    [Route("api/[controller]")]
    public class UsersController
    {
        [HttpPost("/api/v2/users")]
        public void Create() { }
    }
    """
    tree = parser.parse(bytes(code, "utf8"))
    
    class_node = next(c for c in tree.root_node.children if c.type == 'class_declaration')
    class_body = class_node.child_by_field_name('body')
    method_node = next(c for c in class_body.children if c.type == 'method_declaration')
    
    info = analyzer.analyze(class_node, method_node, code)
    
    assert info.http_method == "POST"
    assert info.route_template == "api/v2/users"

def test_non_endpoint(parser, analyzer):
    code = """
    public class Service
    {
        public void DoWork() { }
    }
    """
    tree = parser.parse(bytes(code, "utf8"))
    
    class_node = next(c for c in tree.root_node.children if c.type == 'class_declaration')
    class_body = class_node.child_by_field_name('body')
    method_node = next(c for c in class_body.children if c.type == 'method_declaration')
    
    info = analyzer.analyze(class_node, method_node, code)
    
    assert info is None
