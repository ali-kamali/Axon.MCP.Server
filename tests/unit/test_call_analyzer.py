import pytest
from src.extractors.call_analyzer import CSharpCallAnalyzer, JavaScriptCallAnalyzer
from src.parsers.csharp_parser import CSharpParser
from src.parsers.javascript_parser import JavaScriptParser

class TestCSharpCallAnalyzer:
    @pytest.fixture
    def analyzer(self):
        return CSharpCallAnalyzer()

    @pytest.fixture
    def parser(self):
        return CSharpParser()

    def test_extract_constructor_calls(self, analyzer, parser):
        code = """
        public class TestClass {
            public void Method() {
                var x = new MyClass();
                var y = new List<string>();
                var z = new Dictionary<string, int>();
            }
        }
        """
        tree = parser.parser.parse(bytes(code, "utf8"))
        # Find the method node
        root = tree.root_node
        class_decl = None
        for child in root.children:
            if child.type == 'class_declaration':
                class_decl = child
                break
        
        assert class_decl is not None
        
        method_decl = None
        # Check direct children or declaration_list
        children_to_check = class_decl.children
        decl_list = next((c for c in class_decl.children if c.type == 'declaration_list'), None)
        if decl_list:
            children_to_check = decl_list.children
            
        for child in children_to_check:
            if child.type == 'method_declaration':
                method_decl = child
                break
        
        assert method_decl is not None
        
        calls = analyzer.extract_calls(method_decl, code)
        
        # Should find 3 constructor calls
        assert len(calls) == 3
        
        # Check MyClass
        call1 = next((c for c in calls if c.method_name == "MyClass"), None)
        assert call1 is not None
        assert call1.is_static is True
        
        # Check List
        call2 = next((c for c in calls if c.method_name == "List"), None)
        assert call2 is not None
        assert call2.is_static is True
        
        # Check Dictionary
        call3 = next((c for c in calls if c.method_name == "Dictionary"), None)
        assert call3 is not None
        assert call3.is_static is True

    def test_extract_generic_method_calls(self, analyzer, parser):
        code = """
        public class TestClass {
            public void Method() {
                service.Get<User>(1);
                var x = Mapper.Map<Dto>(entity);
            }
        }
        """
        tree = parser.parser.parse(bytes(code, "utf8"))
        root = tree.root_node
        class_decl = root.children[0]
        method_decl = None
        
        children_to_check = class_decl.children
        decl_list = next((c for c in class_decl.children if c.type == 'declaration_list'), None)
        if decl_list:
            children_to_check = decl_list.children

        for child in children_to_check:
            if child.type == 'method_declaration':
                method_decl = child
                break
        
        calls = analyzer.extract_calls(method_decl, code)
        
        assert len(calls) == 2
        
        # Check Get<User>
        call1 = next((c for c in calls if c.method_name == "Get"), None)
        assert call1 is not None
        assert call1.receiver == "service"
        
        # Check Map<Dto>
        call2 = next((c for c in calls if c.method_name == "Map"), None)
        assert call2 is not None
        assert call2.receiver == "Mapper"

class TestJavaScriptCallAnalyzer:
    @pytest.fixture
    def analyzer(self):
        return JavaScriptCallAnalyzer()

    @pytest.fixture
    def parser(self):
        return JavaScriptParser()

    def test_extract_new_expression(self, analyzer, parser):
        code = """
        function test() {
            const u = new User();
            const d = new Date();
        }
        """
        tree = parser.parser.parse(bytes(code, "utf8"))
        root = tree.root_node
        func_decl = root.children[0]
        
        calls = analyzer.extract_calls(func_decl, code)
        
        assert len(calls) == 2
        
        call1 = next((c for c in calls if c.method_name == "User"), None)
        assert call1 is not None
        assert call1.is_static is True
        
        call2 = next((c for c in calls if c.method_name == "Date"), None)
        assert call2 is not None
        assert call2.is_static is True
