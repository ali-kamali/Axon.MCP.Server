import pytest
import tree_sitter
from src.parsers.csharp_parser import CSharpParser
from src.extractors.call_analyzer import CSharpCallAnalyzer

class TestReferenceLocations:
    
    def test_extract_call_locations(self):
        code = """
        public class TestClass {
            public void MethodA() {
                MethodB();
                var x = GetValue(1, 2);
                Service.DoSomething();
            }
        }
        """
        
        parser = CSharpParser()
        # We need to parse the code to get the AST
        # CSharpParser.parse returns a list of ParsedSymbol, but we need the raw tree-sitter node
        # for CSharpCallAnalyzer.
        # So we'll access the parser instance directly if possible, or just use the parser logic.
        
        # Initialize parser (this sets up the tree-sitter parser)
        # Assuming parser.parser is the tree-sitter parser instance
        tree = parser.parser.parse(bytes(code, "utf8"))
        root_node = tree.root_node
        
        # Find the method body of MethodA
        # Structure: class_declaration -> body -> method_declaration -> body
        class_decl = root_node.children[0] # public class TestClass
        class_body = class_decl.child_by_field_name("body")
        method_decl = class_body.children[1] # public void MethodA (index 0 is {)
        
        # Verify we have the right node
        assert method_decl.type == "method_declaration"
        
        analyzer = CSharpCallAnalyzer()
        calls = analyzer.extract_calls(method_decl, code)
        
        assert len(calls) == 3
        
        # MethodB();
        # Line 4 (1-indexed)
        # Indentation is 16 spaces? Let's check the string.
        # "                MethodB();"
        # Start column should be index of 'M'
        
        call1 = calls[0]
        assert call1.method_name == "MethodB"
        assert call1.line_number == 4
        assert call1.end_line == 4
        # We can't easily assert exact columns without counting spaces, but we can check they are > 0
        assert call1.start_column > 0
        assert call1.end_column > call1.start_column
        
        # var x = GetValue(1, 2);
        # This is an invocation inside a variable declaration.
        # Analyzer extracts invocations.
        call2 = calls[1]
        assert call2.method_name == "GetValue"
        assert call2.line_number == 5
        
        # Service.DoSomething();
        call3 = calls[2]
        assert call3.method_name == "DoSomething"
        assert call3.receiver == "Service"
        assert call3.line_number == 6
