import pytest
from pathlib import Path
from src.parsers import ParserFactory, parse_file
from src.parsers.csharp_parser import CSharpParser
from src.config.enums import SymbolKindEnum, AccessModifierEnum, LanguageEnum

class TestCSharpParser:
    """Test C# parser functionality."""
    
    @pytest.fixture
    def parser(self):
        return CSharpParser()
    
    def test_parse_class(self, parser):
        """Test class parsing."""
        code = """
        public class MyClass {
            public void MyMethod() { }
        }
        """
        result = parser.parse(code, "test.cs")
        
        assert len(result.symbols) >= 1
        class_symbol = next(s for s in result.symbols if s.kind == SymbolKindEnum.CLASS)
        assert class_symbol.name == "MyClass"
        assert class_symbol.access_modifier == AccessModifierEnum.PUBLIC
    
    def test_parse_method(self, parser):
        """Test method parsing."""
        code = """
        public class TestClass {
            public string GetName(int id) { return "test"; }
        }
        """
        result = parser.parse(code)
        
        method = next(s for s in result.symbols if s.kind == SymbolKindEnum.METHOD)
        assert method.name == "GetName"
        assert len(method.parameters) == 1
        assert method.parameters[0]['name'] == 'id'
        assert method.return_type == 'string'
    
    @pytest.mark.parametrize("code,expected_count", [
        ("public class A {}", 1),
        ("public class A {} public class B {}", 2),
    ])
    def test_multiple_classes(self, parser, code, expected_count):
        """Test parsing multiple classes."""
        result = parser.parse(code)
        classes = [s for s in result.symbols if s.kind == SymbolKindEnum.CLASS]
        assert len(classes) == expected_count

class TestJavaScriptParser:
    """Test JavaScript parser functionality."""
    
    @pytest.fixture
    def parser(self):
        from src.parsers.javascript_parser import JavaScriptParser
        return JavaScriptParser()
    
    def test_parse_function(self, parser):
        """Test function parsing."""
        code = "function myFunction(param1, param2) { return param1 + param2; }"
        result = parser.parse(code, "test.js")
        
        assert len(result.symbols) >= 1
        func = result.symbols[0]
        assert func.kind == SymbolKindEnum.FUNCTION
        assert func.name == "myFunction"
        assert len(func.parameters) == 2
    
    def test_parse_arrow_function(self, parser):
        """Test arrow function parsing."""
        code = "const myFunc = (x) => x * 2;"
        result = parser.parse(code)
        
        assert len(result.symbols) >= 1
        func = result.symbols[0]
        assert func.name == "myFunc"
        assert func.kind == SymbolKindEnum.FUNCTION

class TestVueParser:
    """Test Vue parser functionality."""
    
    @pytest.fixture
    def parser(self):
        from src.parsers.vue_parser import VueParser
        return VueParser()
    
    def test_parse_vue_js(self, parser):
        """Test Vue SFC with JavaScript."""
        code = """
        <template>
          <div>Hello</div>
        </template>
        <script>
        export default {
          name: 'MyComponent',
          methods: {
            greet() { }
          }
        }
        </script>
        """
        result = parser.parse(code, "test.vue")
        
        assert result.language == LanguageEnum.VUE
        assert len(result.parse_errors) == 0
    
    def test_parse_vue_ts(self, parser):
        """Test Vue SFC with TypeScript."""
        code = """
        <template>
          <div>Hello</div>
        </template>
        <script lang="ts">
        export default {
          name: 'MyComponent'
        }
        </script>
        """
        result = parser.parse(code, "test.vue")
        
        assert result.language == LanguageEnum.VUE

class TestTypeScriptParser:
    """Test TypeScript parser functionality."""
    
    @pytest.fixture
    def parser(self):
        from src.parsers.javascript_parser import TypeScriptParser
        return TypeScriptParser()
    
    def test_parse_interface(self, parser):
        """Test interface parsing."""
        code = """
        interface MyInterface {
            name: string;
            age: number;
        }
        """
        result = parser.parse(code, "test.ts")
        
        assert len(result.symbols) >= 1
        interface_symbol = next(s for s in result.symbols if s.kind == SymbolKindEnum.INTERFACE)
        assert interface_symbol.name == "MyInterface"
    
    def test_parse_enum(self, parser):
        """Test enum parsing."""
        code = """
        enum Status {
            Pending,
            Completed,
            Failed
        }
        """
        result = parser.parse(code, "test.ts")
        
        assert len(result.symbols) >= 1
        enum_symbol = next(s for s in result.symbols if s.kind == SymbolKindEnum.ENUM)
        assert enum_symbol.name == "Status"
    
    def test_parse_type_alias(self, parser):
        """Test type alias parsing."""
        code = """
        type MyType = string | number;
        """
        result = parser.parse(code, "test.ts")
        
        assert len(result.symbols) >= 1
        type_symbol = next(s for s in result.symbols if s.name == "MyType")
        assert type_symbol.kind == SymbolKindEnum.TYPE_ALIAS  # Type aliases have their own kind now
        assert type_symbol.name == "MyType"
    
    def test_parse_typescript_class(self, parser):
        """Test TypeScript class parsing."""
        code = """
        class MyClass {
            private name: string;
            public getName(): string {
                return this.name;
            }
        }
        """
        result = parser.parse(code, "test.ts")
        
        assert len(result.symbols) >= 1
        class_symbol = next(s for s in result.symbols if s.kind == SymbolKindEnum.CLASS)
        assert class_symbol.name == "MyClass"
    
    def test_parse_tsx_with_jsx(self, parser):
        """Test TSX file with JSX syntax."""
        # Create TSX-aware parser
        from src.parsers.javascript_parser import TypeScriptParser
        tsx_parser = TypeScriptParser(use_tsx=True)
        
        code = """
        import React from 'react';
        
        interface Props {
            name: string;
        }
        
        export const MyComponent: React.FC<Props> = ({ name }) => {
            return <div className="container">
                <h1>Hello {name}</h1>
            </div>;
        };
        """
        result = tsx_parser.parse(code, "test.tsx")
        
        # Should parse without errors and extract the interface and function
        assert len(result.parse_errors) == 0
        assert len(result.symbols) >= 1
        
        # Should find the Props interface
        interface_symbols = [s for s in result.symbols if s.kind == SymbolKindEnum.INTERFACE]
        assert len(interface_symbols) == 1
        assert interface_symbols[0].name == "Props"

class TestParserFactory:
    """Test parser factory."""
    
    def test_get_parser_for_file(self):
        """Test getting correct parser for file."""
        parser = ParserFactory.get_parser_for_file(Path("test.cs"))
        assert isinstance(parser, CSharpParser)
    
    def test_unsupported_file_raises_error(self):
        """Test unsupported file type raises error."""
        with pytest.raises(ValueError):
            ParserFactory.get_parser_for_file(Path("test.txt"))

