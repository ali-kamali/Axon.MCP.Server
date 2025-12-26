
import pytest
import asyncio
import sys
import os
from unittest.mock import MagicMock, AsyncMock, patch
import json
from datetime import datetime

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.extractors.config_extractor import ConfigExtractor
from src.extractors.call_analyzer import CSharpCallAnalyzer, Call
from src.extractors.call_resolver import CallResolver
from src.extractors.relationship_builder import RelationshipBuilder
from src.database.models import Symbol, File, Relation, ConfigurationEntry
from src.config.enums import SymbolKindEnum, RelationTypeEnum, LanguageEnum
import tree_sitter_c_sharp as tscsharp
from tree_sitter import Language, Parser

# --- ConfigExtractor Tests ---

@pytest.mark.asyncio
async def test_config_extractor_flattening():
    extractor = ConfigExtractor(None)
    json_content = """
    {
        "Section": {
            "SubSection": {
                "Key": "Value"
            }
        },
        "Array": [1, 2, 3],
        "Boolean": true,
        "Null": null
    }
    """
    entries = extractor._parse_json_config(json_content)
    assert entries["Section:SubSection:Key"] == "Value"
    assert entries["Array"] == [1, 2, 3]
    assert entries["Boolean"] is True
    assert entries["Null"] is None

@pytest.mark.asyncio
async def test_config_extractor_secrets():
    extractor = ConfigExtractor(None)
    assert extractor._is_potential_secret("MyPassword", "123456") is True
    assert extractor._is_potential_secret("ApiKey", "abcdef") is True
    assert extractor._is_potential_secret("ConnectionStrings:Default", "Server=...") is False # Might need tuning
    # Actually, 'ConnectionStrings' usually contains secrets but the key itself doesn't have 'password'
    # The current logic checks if key contains keywords.
    assert extractor._is_potential_secret("AuthToken", "xyz") is True
    assert extractor._is_potential_secret("Timeout", "30") is False

# --- CSharpCallAnalyzer Tests ---

def parse_csharp(code):
    CSHARP_LANGUAGE = Language(tscsharp.language())
    parser = Parser(CSHARP_LANGUAGE)
    return parser.parse(bytes(code, "utf8"))

def get_method_node(tree):
    root = tree.root_node
    # Assuming class -> body -> method
    class_node = root.children[0]
    class_body = class_node.child_by_field_name('body')
    for child in class_body.children:
        if child.type == 'method_declaration':
            return child
    return None

def test_csharp_extract_usages_variables():
    analyzer = CSharpCallAnalyzer()
    code = """
    public class Test {
        public void Method() {
            var x = 10;
            var y = x + 5;
            Console.WriteLine(y);
        }
    }
    """
    tree = parse_csharp(code)
    method_node = get_method_node(tree)
    usages = analyzer.extract_usages(method_node, code)
    names = [u.method_name for u in usages]
    
    # x is used in 'x + 5'
    # y is used in 'Console.WriteLine(y)'
    # Console is a usage (identifier)
    # WriteLine is NOT a usage (it's the function called)
    
    assert "x" in names
    assert "y" in names
    assert "Console" in names
    assert "WriteLine" not in names

def test_csharp_extract_usages_properties():
    analyzer = CSharpCallAnalyzer()
    code = """
    public class Test {
        public void Method() {
            var val = this.MyProp;
            var other = _service.Data;
        }
    }
    """
    tree = parse_csharp(code)
    method_node = get_method_node(tree)
    usages = analyzer.extract_usages(method_node, code)
    names = [u.method_name for u in usages]
    
    # this.MyProp -> MyProp is usage
    # _service.Data -> _service is usage, Data is usage
    
    assert "MyProp" in names
    assert "_service" in names
    assert "Data" in names

def test_csharp_extract_usages_arguments():
    analyzer = CSharpCallAnalyzer()
    code = """
    public class Test {
        public void Method() {
            DoSomething(myVar);
        }
    }
    """
    tree = parse_csharp(code)
    method_node = get_method_node(tree)
    usages = analyzer.extract_usages(method_node, code)
    names = [u.method_name for u in usages]
    
    assert "myVar" in names
    assert "DoSomething" not in names

# --- CallResolver Tests ---

@pytest.mark.asyncio
async def test_resolve_usage_target_local_property():
    session = AsyncMock()
    resolver = CallResolver(session)
    
    # Mock data
    calling_symbol = Symbol(id=1, parent_name="MyNamespace.MyClass")
    file = File(id=1, repository_id=1)
    
    # Mock _find_member_in_class
    target_symbol = Symbol(id=2, name="MyProp", kind=SymbolKindEnum.PROPERTY)
    resolver._find_member_in_class = AsyncMock(return_value=target_symbol)
    
    result_id = await resolver.resolve_usage_target("MyProp", calling_symbol, file)
    
    assert result_id == 2
    resolver._find_member_in_class.assert_called_with("MyProp", "MyNamespace.MyClass", 1)

@pytest.mark.asyncio
async def test_resolve_usage_target_static_member():
    session = AsyncMock()
    resolver = CallResolver(session)
    
    calling_symbol = Symbol(id=1, parent_name="MyNamespace.MyClass")
    file = File(id=1, repository_id=1)
    
    # Mock _find_member_in_class to return None (so it proceeds to next strategy)
    resolver._find_member_in_class = AsyncMock(return_value=None)
    
    # Mock _find_qualified_member
    target_symbol = Symbol(id=3, name="StaticProp", kind=SymbolKindEnum.PROPERTY)
    resolver._find_qualified_member = AsyncMock(return_value=target_symbol)
    
    result_id = await resolver.resolve_usage_target("OtherClass.StaticProp", calling_symbol, file)
    
    assert result_id == 3
    resolver._find_qualified_member.assert_called()

# --- RelationshipBuilder Tests ---

@pytest.mark.asyncio
async def test_build_reference_relationships():
    session = AsyncMock()
    builder = RelationshipBuilder(session)
    
    # Symbols
    # Class User
    user_sym = Symbol(id=1, name="User", fully_qualified_name="App.User", kind=SymbolKindEnum.CLASS)
    # Method GetUser returns User
    method_sym = Symbol(id=2, name="GetUser", return_type="User", kind=SymbolKindEnum.METHOD)
    # Method SaveUser takes User
    method_sym2 = Symbol(id=3, name="SaveUser", parameters=[{"name": "u", "type": "User"}], kind=SymbolKindEnum.METHOD)
    
    symbols = [user_sym, method_sym, method_sym2]
    symbol_index = {"User": [user_sym]}
    
    # Mock _resolve_type
    builder._resolve_type = MagicMock(side_effect=lambda name, idx: idx.get(name, []))
    
    count = await builder._build_reference_relationships(symbols, symbol_index)
    
    assert count == 2 # GetUser -> User, SaveUser -> User
    
    # Verify calls to session.add
    assert session.add.call_count == 2
    
    # Verify relations
    calls = session.add.call_args_list
    relations = [c[0][0] for c in calls]
    
    assert any(r.from_symbol_id == 2 and r.to_symbol_id == 1 and r.relation_type == RelationTypeEnum.REFERENCES for r in relations)
    assert any(r.from_symbol_id == 3 and r.to_symbol_id == 1 and r.relation_type == RelationTypeEnum.REFERENCES for r in relations)

if __name__ == "__main__":
    # Manually run tests if executed as script
    asyncio.run(test_config_extractor_flattening())
    asyncio.run(test_config_extractor_secrets())
    test_csharp_extract_usages_variables()
    test_csharp_extract_usages_properties()
    test_csharp_extract_usages_arguments()
    asyncio.run(test_resolve_usage_target_local_property())
    asyncio.run(test_resolve_usage_target_static_member())
    asyncio.run(test_build_reference_relationships())
    print("All tests passed!")
