"""Test if CSharpCallAnalyzer can detect calls in simple code."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.extractors.call_analyzer import CSharpCallAnalyzer
from src.parsers import ParserFactory
from src.config.enums import LanguageEnum


def test_simple_call():
    """Test with simple C# code."""
    
    code = """
    public class TestClass
    {
        public void MethodA()
        {
            MethodB();
            var result = MethodC("test");
            this.MethodD();
        }
        
        public void MethodB() { }
        public string MethodC(string arg) { return arg; }
        public void MethodD() { }
    }
    """
    
    print("Testing CSharpCallAnalyzer with simple code...")
    print("=" * 60)
    
    # Parse
    parser = ParserFactory.get_parser(LanguageEnum.CSHARP)
    
    # Handle both HybridCSharpParser and regular parser
    if hasattr(parser, 'tree_sitter'):
        # Hybrid parser has tree_sitter attribute which is the CSharpParser
        tree = parser.tree_sitter.parser.parse(bytes(code, "utf8"))
    elif hasattr(parser, 'tree_sitter_parser'):
        tree = parser.tree_sitter_parser.parse(bytes(code, "utf8"))
    elif hasattr(parser, 'parser'):
        tree = parser.parser.parse(bytes(code, "utf8"))
    else:
        print("[FAIL] Parser doesn't have expected attributes")
        return
    
    # Find MethodA
    def find_method(node, name):
        if node.type == 'method_declaration':
            for child in node.children:
                if child.type == 'identifier' and code[child.start_byte:child.end_byte] == name:
                    return node
        for child in node.children:
            result = find_method(child, name)
            if result:
                return result
        return None
    
    method_a = find_method(tree.root_node, 'MethodA')
    
    if not method_a:
        print("[FAIL] Could not find MethodA in parsed tree")
        return
    
    print("[OK] Found MethodA in tree")
    
    # Extract calls
    analyzer = CSharpCallAnalyzer()
    calls = analyzer.extract_calls(method_a, code)
    
    print(f"\n[INFO] Detected {len(calls)} calls:")
    for call in calls:
        receiver_str = f"{call.receiver}." if call.receiver else ""
        print(f"   - {receiver_str}{call.method_name}() at line {call.line_number}")
    
    if len(calls) == 0:
        print("\n[FAIL] PROBLEM: No calls detected!")
        print("   The CSharpCallAnalyzer is not working correctly.")
    elif len(calls) < 3:
        print(f"\n[WARN] WARNING: Only {len(calls)} calls detected, expected 3")
        print("   The analyzer might be missing some call patterns.")
    else:
        print("\n[OK] Call detection is working!")


if __name__ == "__main__":
    test_simple_call()
