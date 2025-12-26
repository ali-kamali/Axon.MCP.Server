"""
Tests for enhanced C# attribute parsing.

Tests Phase 3.3: Enhanced Attribute Parsing
- Named parameters
- Complex expressions in attributes
- Array/collection arguments
- typeof expressions
- Member access expressions
"""

import pytest
from pathlib import Path
from src.parsers.csharp_parser import CSharpParser


class TestEnhancedAttributeParsing:
    """Test enhanced attribute argument parsing."""
    
    def setup_method(self):
        """Initialize parser for each test."""
        self.parser = CSharpParser()
    
    def test_simple_positional_argument(self):
        """Test attribute with simple positional argument."""
        code = '''
        public class TestClass {
            [HttpGet("{id}")]
            public IActionResult GetUser(int id) { }
        }
        '''
        
        result = self.parser.parse(code, Path("test.cs"))
        method = next((s for s in result.symbols if s.name == "GetUser"), None)
        
        assert method is not None
        assert method.structured_docs is not None
        assert 'attributes' in method.structured_docs
        attrs = method.structured_docs['attributes']
        assert len(attrs) == 1
        assert attrs[0]['name'] == 'HttpGet'
        assert attrs[0]['arguments']['positional'] == ['{id}']
        assert attrs[0]['arguments']['named'] == {}
    
    def test_named_parameters(self):
        """Test attribute with named parameters."""
        code = '''
        public class TestClass {
            [Route(Name = "GetUser", Template = "users/{id}")]
            public IActionResult GetUser(int id) { }
        }
        '''
        
        result = self.parser.parse(code, Path("test.cs"))
        method = next((s for s in result.symbols if s.name == "GetUser"), None)
        
        assert method is not None
        attrs = method.structured_docs['attributes']
        assert len(attrs) == 1
        assert attrs[0]['name'] == 'Route'
        assert attrs[0]['arguments']['named']['Name'] == 'GetUser'
        assert attrs[0]['arguments']['named']['Template'] == 'users/{id}'
    
    def test_mixed_positional_and_named(self):
        """Test attribute with both positional and named arguments."""
        code = '''
        public class TestClass {
            [ProducesResponseType(typeof(UserDto), StatusCode = 200)]
            public IActionResult GetUser() { }
        }
        '''
        
        result = self.parser.parse(code, Path("test.cs"))
        method = next((s for s in result.symbols if s.name == "GetUser"), None)
        
        assert method is not None
        attrs = method.structured_docs['attributes']
        assert len(attrs) == 1
        attr = attrs[0]
        assert attr['name'] == 'ProducesResponseType'
        assert len(attr['arguments']['positional']) == 1
        assert attr['arguments']['positional'][0]['type'] == 'typeof'
        assert 'UserDto' in attr['arguments']['positional'][0]['value']
        assert 'StatusCode' in attr['arguments']['named']
    
    def test_authorize_with_policy(self):
        """Test Authorize attribute with Policy named parameter."""
        code = '''
        public class TestClass {
            [Authorize(Policy = "AdminOnly")]
            public IActionResult DeleteUser() { }
        }
        '''
        
        result = self.parser.parse(code, Path("test.cs"))
        method = next((s for s in result.symbols if s.name == "DeleteUser"), None)
        
        assert method is not None
        attrs = method.structured_docs['attributes']
        assert len(attrs) == 1
        assert attrs[0]['name'] == 'Authorize'
        assert attrs[0]['arguments']['named']['Policy'] == 'AdminOnly'
    
    def test_authorize_with_roles(self):
        """Test Authorize attribute with Roles named parameter."""
        code = '''
        public class TestClass {
            [Authorize(Roles = "Admin,User")]
            public IActionResult GetData() { }
        }
        '''
        
        result = self.parser.parse(code, Path("test.cs"))
        method = next((s for s in result.symbols if s.name == "GetData"), None)
        
        assert method is not None
        attrs = method.structured_docs['attributes']
        assert attrs[0]['arguments']['named']['Roles'] == 'Admin,User'
    
    def test_typeof_expression(self):
        """Test typeof expression in attribute argument."""
        code = '''
        public class TestClass {
            [ProducesResponseType(typeof(UserDto), 200)]
            public IActionResult GetUser() { }
        }
        '''
        
        result = self.parser.parse(code, Path("test.cs"))
        method = next((s for s in result.symbols if s.name == "GetUser"), None)
        
        assert method is not None
        attrs = method.structured_docs['attributes']
        assert len(attrs[0]['arguments']['positional']) == 2
        
        # First argument should be typeof
        first_arg = attrs[0]['arguments']['positional'][0]
        assert isinstance(first_arg, dict)
        assert first_arg['type'] == 'typeof'
        assert 'UserDto' in first_arg['value']
        
        # Second argument should be number
        second_arg = attrs[0]['arguments']['positional'][1]
        assert second_arg == 200
    
    def test_member_access_expression(self):
        """Test member access expression (enum value, constant) in attribute."""
        code = '''
        public class TestClass {
            [ProducesResponseType(typeof(UserDto), StatusCodes.Status200OK)]
            public IActionResult GetUser() { }
        }
        '''
        
        result = self.parser.parse(code, Path("test.cs"))
        method = next((s for s in result.symbols if s.name == "GetUser"), None)
        
        assert method is not None
        attrs = method.structured_docs['attributes']
        args = attrs[0]['arguments']['positional']
        
        # Second argument should be member access
        second_arg = args[1]
        assert isinstance(second_arg, dict)
        assert second_arg['type'] == 'member_access'
        assert second_arg['value'] == 'StatusCodes.Status200OK'
    
    def test_multiple_attributes_on_same_member(self):
        """Test multiple attributes on the same member."""
        code = '''
        public class TestClass {
            [HttpGet("{id}")]
            [Authorize(Policy = "ReadUsers")]
            [ProducesResponseType(typeof(UserDto), 200)]
            public IActionResult GetUser(int id) { }
        }
        '''
        
        result = self.parser.parse(code, Path("test.cs"))
        method = next((s for s in result.symbols if s.name == "GetUser"), None)
        
        assert method is not None
        attrs = method.structured_docs['attributes']
        assert len(attrs) == 3
        
        # Check each attribute
        attr_names = [attr['name'] for attr in attrs]
        assert 'HttpGet' in attr_names
        assert 'Authorize' in attr_names
        assert 'ProducesResponseType' in attr_names
    
    def test_attribute_without_arguments(self):
        """Test attribute without any arguments."""
        code = '''
        [ApiController]
        public class UsersController { }
        '''
        
        result = self.parser.parse(code, Path("test.cs"))
        cls = next((s for s in result.symbols if s.name == "UsersController"), None)
        
        assert cls is not None
        attrs = cls.structured_docs['attributes']
        assert len(attrs) == 1
        assert attrs[0]['name'] == 'ApiController'
        assert attrs[0]['arguments']['positional'] == []
        assert attrs[0]['arguments']['named'] == {}
    
    def test_route_on_controller_class(self):
        """Test Route attribute on controller class."""
        code = '''
        [ApiController]
        [Route("api/[controller]")]
        public class UsersController : ControllerBase { }
        '''
        
        result = self.parser.parse(code, Path("test.cs"))
        cls = next((s for s in result.symbols if s.name == "UsersController"), None)
        
        assert cls is not None
        attrs = cls.structured_docs['attributes']
        route_attr = next((a for a in attrs if a['name'] == 'Route'), None)
        
        assert route_attr is not None
        assert route_attr['arguments']['positional'] == ['api/[controller]']
    
    def test_maxlength_validation_attribute(self):
        """Test validation attribute with numeric argument."""
        code = '''
        public class UserDto
        {
            [MaxLength(50)]
            public string Name { get; set; }
        }
        '''
        
        result = self.parser.parse(code, Path("test.cs"))
        prop = next((s for s in result.symbols if s.name == "Name"), None)
        
        assert prop is not None
        attrs = prop.structured_docs['attributes']
        assert len(attrs) == 1
        assert attrs[0]['name'] == 'MaxLength'
        assert attrs[0]['arguments']['positional'] == [50]
    
    def test_boolean_attribute_argument(self):
        """Test attribute with boolean argument."""
        code = '''
        public class TestClass {
            [Required(AllowEmptyStrings = false)]
            public string Email { get; set; }
        }
        '''
        
        result = self.parser.parse(code, Path("test.cs"))
        prop = next((s for s in result.symbols if s.name == "Email"), None)
        
        assert prop is not None
        attrs = prop.structured_docs['attributes']
        assert attrs[0]['arguments']['named']['AllowEmptyStrings'] is False
    
    def test_api_version_attribute(self):
        """Test API versioning attribute."""
        code = '''
        [ApiVersion("1.0")]
        [ApiVersion("2.0")]
        public class UsersController { }
        '''
        
        result = self.parser.parse(code, Path("test.cs"))
        cls = next((s for s in result.symbols if s.name == "UsersController"), None)
        
        assert cls is not None
        attrs = cls.structured_docs['attributes']
        version_attrs = [a for a in attrs if a['name'] == 'ApiVersion']
        assert len(version_attrs) == 2
        assert version_attrs[0]['arguments']['positional'] == ['1.0']
        assert version_attrs[1]['arguments']['positional'] == ['2.0']


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
