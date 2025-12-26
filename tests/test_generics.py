import pytest
from unittest.mock import MagicMock
from src.parsers.csharp_parser import CSharpParser
from src.config.enums import SymbolKindEnum
import tree_sitter
import tree_sitter_c_sharp

class TestGenericsExtraction:
    
    def setup_method(self):
        self.parser = CSharpParser()

    def test_generic_class_definition(self):
        code = """
        public class Repository<T> where T : IEntity
        {
            public T Get(int id);
        }
        """
        # Parse manually to avoid file system dependency
        language = tree_sitter.Language(tree_sitter_c_sharp.language())
        ts_parser = tree_sitter.Parser(language)
        tree = ts_parser.parse(bytes(code, "utf8"))
        
        symbols = self.parser._extract_symbols(tree.root_node, code)
        
        repo_class = next(s for s in symbols if s.name == "Repository")
        
        # Check generic parameters
        assert len(repo_class.generic_parameters) == 1
        assert repo_class.generic_parameters[0]['name'] == "T"
        
        # Check constraints
        assert len(repo_class.constraints) == 1
        assert repo_class.constraints[0]['parameter'] == "T"
        assert "IEntity" in repo_class.constraints[0]['constraints']

    def test_generic_method(self):
        code = """
        public class Mapper {
            public TResult Map<TSource, TResult>(TSource source) where TResult : new()
            {
                return new TResult();
            }
        }
        """
        language = tree_sitter.Language(tree_sitter_c_sharp.language())
        ts_parser = tree_sitter.Parser(language)
        tree = ts_parser.parse(bytes(code, "utf8"))
        
        symbols = self.parser._extract_symbols(tree.root_node, code)
        
        map_method = next(s for s in symbols if s.name == "Map")
        
        # Check generic parameters
        assert len(map_method.generic_parameters) == 2
        names = [p['name'] for p in map_method.generic_parameters]
        assert "TSource" in names
        assert "TResult" in names
        
        # Check constraints
        assert len(map_method.constraints) == 1
        assert map_method.constraints[0]['parameter'] == "TResult"
        assert "new()" in map_method.constraints[0]['constraints']

    def test_variance(self):
        code = """
        public interface IEnumerable<out T>
        {
            T GetEnumerator();
        }
        """
        language = tree_sitter.Language(tree_sitter_c_sharp.language())
        ts_parser = tree_sitter.Parser(language)
        tree = ts_parser.parse(bytes(code, "utf8"))
        
        symbols = self.parser._extract_symbols(tree.root_node, code)
        
        iface = next(s for s in symbols if s.name == "IEnumerable")
        
        assert len(iface.generic_parameters) == 1
        assert iface.generic_parameters[0]['name'] == "T"
        assert iface.generic_parameters[0]['variance'] == "out"

if __name__ == "__main__":
    # Manual run helper
    t = TestGenericsExtraction()
    t.setup_method()
    
    print("Testing Generic Class...")
    try:
        t.test_generic_class_definition()
        print("[PASS]")
    except Exception as e:
        print(f"[FAIL] {e}")
        import traceback
        traceback.print_exc()
        
    print("Testing Generic Method...")
    try:
        t.test_generic_method()
        print("[PASS]")
    except Exception as e:
        print(f"[FAIL] {e}")
        import traceback
        traceback.print_exc()

    print("Testing Variance...")
    try:
        t.test_variance()
        print("[PASS]")
    except Exception as e:
        print(f"[FAIL] {e}")
        import traceback
        traceback.print_exc()
