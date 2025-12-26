import pytest
import tree_sitter_c_sharp
from src.extractors.call_analyzer import CSharpCallAnalyzer
from src.parsers.csharp_parser import CSharpParser

class TestCSharpCallAnalyzerUsages:
    @pytest.fixture
    def analyzer(self):
        return CSharpCallAnalyzer()

    @pytest.fixture
    def parser(self):
        return CSharpParser()

    def test_extract_property_access(self, analyzer, parser):
        code = """
        public class TestClass {
            public void Method(User user) {
                var name = user.Name;
                var id = user.Id;
            }
        }
        """
        tree = parser.parser.parse(bytes(code, "utf8"))
        # Find method node
        root = tree.root_node
        class_decl = root.children[0]
        # In newer tree-sitter, body might be in declaration_list
        method_decl = None
        
        # Navigate to method declaration
        # Simplified navigation for test
        cursor = class_decl.walk()
        
        def find_method(node):
            if node.type == 'method_declaration':
                return node
            for child in node.children:
                res = find_method(child)
                if res: return res
            return None
            
        method_decl = find_method(class_decl)
        assert method_decl is not None
        
        usages = analyzer.extract_usages(method_decl, code)
        
        # We expect:
        # 1. user (receiver=None)
        # 2. Name (receiver="user")
        # 3. user (receiver=None) - second usage
        # 4. Id (receiver="user")
        
        # Filter for "Name"
        name_usage = next((u for u in usages if u.method_name == "Name"), None)
        assert name_usage is not None
        assert name_usage.receiver == "user"
        
        # Filter for "Id"
        id_usage = next((u for u in usages if u.method_name == "Id"), None)
        assert id_usage is not None
        assert id_usage.receiver == "user"

    def test_extract_field_access_this(self, analyzer, parser):
        code = """
        public class TestClass {
            private string _field;
            
            public void Method() {
                var val = this._field;
            }
        }
        """
        tree = parser.parser.parse(bytes(code, "utf8"))
        root = tree.root_node
        class_decl = root.children[0]
        method_decl = None
        
        def find_method(node):
            if node.type == 'method_declaration':
                return node
            for child in node.children:
                res = find_method(child)
                if res: return res
            return None
        
        method_decl = find_method(class_decl)
        assert method_decl is not None
        
        usages = analyzer.extract_usages(method_decl, code)
        
        # Expect _field with receiver 'this'
        field_usage = next((u for u in usages if u.method_name == "_field"), None)
        assert field_usage is not None
        assert field_usage.receiver == "this"

    def test_extract_implicit_this_property(self, analyzer, parser):
        code = """
        public class TestClass {
            public string Prop { get; set; }
            
            public void Method() {
                var val = Prop;
            }
        }
        """
        tree = parser.parser.parse(bytes(code, "utf8"))
        root = tree.root_node
        class_decl = root.children[0]
        method_decl = None
        
        def find_method(node):
            if node.type == 'method_declaration':
                return node
            for child in node.children:
                res = find_method(child)
                if res: return res
            return None
        
        method_decl = find_method(class_decl)
        assert method_decl is not None
        
        usages = analyzer.extract_usages(method_decl, code)
        
        # Expect Prop with receiver None
        prop_usage = next((u for u in usages if u.method_name == "Prop"), None)
        assert prop_usage is not None
        assert prop_usage.receiver is None

    def test_extract_chained_access(self, analyzer, parser):
        code = """
        public class TestClass {
            public void Method(User user) {
                var city = user.Address.City;
            }
        }
        """
        tree = parser.parser.parse(bytes(code, "utf8"))
        root = tree.root_node
        class_decl = root.children[0]
        method_decl = None
        
        def find_method(node):
            if node.type == 'method_declaration':
                return node
            for child in node.children:
                res = find_method(child)
                if res: return res
            return None
        
        method_decl = find_method(class_decl)
        assert method_decl is not None
        
        usages = analyzer.extract_usages(method_decl, code)
        
        # We expect:
        # user (None)
        # Address (user)
        # City (user.Address)
        
        city_usage = next((u for u in usages if u.method_name == "City"), None)
        assert city_usage is not None
        assert city_usage.receiver == "user.Address"

    def test_extract_constructor_param_types(self, analyzer, parser):
        code = """
        public class TestClass {
            public TestClass(IUserService service) {
            }
        }
        """
        tree = parser.parser.parse(bytes(code, "utf8"))
        root = tree.root_node
        class_decl = root.children[0]
        
        # Find constructor
        ctor_decl = None
        def find_ctor(node):
            if node.type == 'constructor_declaration':
                return node
            for child in node.children:
                res = find_ctor(child)
                if res: return res
            return None
            
        ctor_decl = find_ctor(class_decl)
        assert ctor_decl is not None
        
        usages = analyzer.extract_usages(ctor_decl, code)
        
        # Expect IUserService as a usage (type ref)
        type_usage = next((u for u in usages if u.method_name == "IUserService"), None)
        assert type_usage is not None
        assert type_usage.is_static is True

    def test_extract_field_initializer(self, analyzer, parser):
        code = """
        public class TestClass {
            private IService _service = new Service();
        }
        """
        tree = parser.parser.parse(bytes(code, "utf8"))
        root = tree.root_node
        class_decl = root.children[0]
        
        # Find field declaration
        field_decl = None
        def find_field(node):
            if node.type == 'field_declaration':
                return node
            for child in node.children:
                res = find_field(child)
                if res: return res
            return None
            
        field_decl = find_field(class_decl)
        assert field_decl is not None
        
        # Note: 'new Service()' is a Call, not a Usage.
        # But if we access a static property? `private int x = Config.Value;`
        # Or if we use a variable? `private int y = x;`
        
        # Let's test `extract_calls` for `new Service()` (implicit check that analyzer supports field node)
        calls = analyzer.extract_calls(field_decl, code)
        service_call = next((c for c in calls if c.method_name == "Service"), None)
        assert service_call is not None
        
    def test_extract_field_usage_in_initializer(self, analyzer, parser):
        code = """
        public class TestClass {
            private static int Const = 10;
            private int Val = Const;
        }
        """
        tree = parser.parser.parse(bytes(code, "utf8"))
        root = tree.root_node
        class_decl = root.children[0]
        
        # Find second field (Val)
        field_decl = None
        cursor = class_decl.walk()
        
        fields = []
        def find_fields(node):
            if node.type == 'field_declaration':
                fields.append(node)
            for child in node.children:
                find_fields(child)
        
        find_fields(class_decl)
        assert len(fields) >= 2
        field_decl = fields[1] # Val
        
        usages = analyzer.extract_usages(field_decl, code)
        
        # Expect usage of 'Const'
        const_usage = next((u for u in usages if u.method_name == "Const"), None)
        assert const_usage is not None

    def test_extract_property_initializer_usage(self, analyzer, parser):
        code = """
        public class TestClass {
            public int Prop { get; set; } = Config.Value;
        }
        """
        tree = parser.parser.parse(bytes(code, "utf8"))
        root = tree.root_node
        class_decl = root.children[0]
        
        prop_decl = None
        def find_prop(node):
            if node.type == 'property_declaration':
                return node
            for child in node.children:
                find_prop(child)
                if prop_decl: return
            if node.type == 'property_declaration': # wait, logic
                 pass
        
        # Simplify finding
        cursor = class_decl.walk()
        # Assume it's structurally simple for test
        # class_decl -> body -> property_declaration
        # or class_decl -> declaration_list -> property_declaration
        
        def simple_find(node, t):
            if node.type == t: return node
            for c in node.children:
                r = simple_find(c, t)
                if r: return r
            return None

        prop_decl = simple_find(class_decl, 'property_declaration')
        assert prop_decl is not None
        
        usages = analyzer.extract_usages(prop_decl, code)
        
        # Config (receiver=None) and Value (receiver=Config)
        config_usage = next((u for u in usages if u.method_name == "Config"), None)
        assert config_usage is not None
        
        value_usage = next((u for u in usages if u.method_name == "Value"), None)
        assert value_usage is not None
        assert value_usage.receiver == "Config"

