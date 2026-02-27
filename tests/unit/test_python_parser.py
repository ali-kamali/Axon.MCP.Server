from pathlib import Path

from src.config.enums import LanguageEnum, SymbolKindEnum
from src.parsers import ParserFactory
from src.parsers.python_parser import PythonParser


def test_parser_factory_supports_python_files():
    parser = ParserFactory.get_parser_for_file(Path("sample.py"))
    assert isinstance(parser, PythonParser)


def test_get_parser_by_language_python():
    parser = ParserFactory.get_parser(LanguageEnum.PYTHON)
    assert isinstance(parser, PythonParser)


def test_python_parser_extracts_symbols_imports_and_exports():
    parser = PythonParser()
    code = '''
import os
from typing import List

__all__ = ["MyService", "helper"]

CONSTANT_VALUE = 42
runtime_value = "x"

class MyService(BaseService):
    """Service docs."""

    def run(self, items: List[str]) -> int:
        return len(items)


def helper(name: str) -> str:
    """Helper docs."""
    return name.upper()
'''

    result = parser.parse(code, "sample.py")

    assert result.success
    assert result.language == LanguageEnum.PYTHON
    assert "os" in result.imports
    assert "typing.List" in result.imports
    assert "MyService" in result.exports
    assert "helper" in result.exports

    names = {s.name: s for s in result.symbols}
    assert "MyService" in names
    assert names["MyService"].kind == SymbolKindEnum.CLASS

    assert "run" in names
    assert names["run"].kind == SymbolKindEnum.METHOD
    assert names["run"].fully_qualified_name == "MyService.run"

    assert "helper" in names
    assert names["helper"].kind == SymbolKindEnum.FUNCTION

    assert "CONSTANT_VALUE" in names
    assert names["CONSTANT_VALUE"].kind == SymbolKindEnum.CONSTANT


def test_python_parser_handles_module_annotated_assignments_and_all_augmentation():
    parser = PythonParser()
    code = '''
__all__ = ["BASE"]
__all__ += ["EXTRA"]

BASE: int = 1
EXTRA: str
_runtime_flag: bool = False
'''

    result = parser.parse(code, "annotated.py")

    assert result.success
    assert "BASE" in result.exports
    assert "EXTRA" in result.exports

    names = {s.name: s for s in result.symbols}
    assert names["BASE"].kind == SymbolKindEnum.CONSTANT
    assert names["EXTRA"].kind == SymbolKindEnum.CONSTANT
    assert names["_runtime_flag"].kind == SymbolKindEnum.VARIABLE


def test_python_parser_handles_syntax_error_without_crashing():
    parser = PythonParser()
    result = parser.parse("def broken(:\n    pass\n", "broken.py")

    assert not result.success
    assert result.parse_errors
