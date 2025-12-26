# Code Parsers

Multi-language code parser framework using Tree-sitter for extracting symbols and metadata from source code.

## Supported Languages

- **C#** (.cs) - Classes, interfaces, structs, enums, methods, properties, fields
- **JavaScript** (.js, .jsx, .mjs) - Functions, classes, methods
- **TypeScript** (.ts, .tsx) - All JavaScript features + interfaces, type aliases, enums
- **Vue.js** (.vue) - Single File Components with JavaScript/TypeScript

## Quick Start

```python
from pathlib import Path
from src.parsers import parse_file, ParserFactory
from src.config.enums import LanguageEnum

# Parse a file directly
result = parse_file(Path("MyClass.cs"))
print(f"Found {len(result.symbols)} symbols")

# Or get a parser for a specific language
parser = ParserFactory.get_parser(LanguageEnum.CSHARP)
code = "public class MyClass { }"
result = parser.parse(code, "test.cs")

# Access parsed symbols
for symbol in result.symbols:
    print(f"{symbol.kind.value}: {symbol.name} at line {symbol.start_line}")
    if symbol.parameters:
        print(f"  Parameters: {[p['name'] for p in symbol.parameters]}")
```

## API Reference

### ParseResult

Result of parsing a file:

```python
@dataclass
class ParseResult:
    language: LanguageEnum        # Language of the code
    file_path: str                # Path to the file
    symbols: List[ParsedSymbol]   # Extracted symbols
    imports: List[str]            # Import statements
    exports: List[str]            # Export statements
    parse_errors: List[str]       # Any errors encountered
    parse_duration_ms: float      # Time taken to parse
```

### ParsedSymbol

Represents a code symbol:

```python
@dataclass
class ParsedSymbol:
    kind: SymbolKindEnum              # CLASS, METHOD, FUNCTION, etc.
    name: str                         # Symbol name
    start_line: int                   # Starting line number
    end_line: int                     # Ending line number
    start_column: int                 # Starting column
    end_column: int                   # Ending column
    signature: Optional[str]          # Full signature
    documentation: Optional[str]      # Documentation comment
    parameters: List[Dict[str, Any]]  # Method/function parameters
    return_type: Optional[str]        # Return type
    access_modifier: Optional[...]    # PUBLIC, PRIVATE, etc.
    parent_name: Optional[str]        # Parent symbol name
    fully_qualified_name: Optional[str]  # Full qualified name
```

## Symbol Kinds

Defined in `src.config.enums.SymbolKindEnum`:

- `CLASS` - Class declaration
- `INTERFACE` - Interface declaration
- `STRUCT` - Struct declaration
- `ENUM` - Enum declaration
- `METHOD` - Method inside a class
- `FUNCTION` - Standalone function
- `PROPERTY` - Property/getter/setter
- `VARIABLE` - Field or variable

## Access Modifiers

Defined in `src.config.enums.AccessModifierEnum`:

- `PUBLIC` - Public access
- `PRIVATE` - Private access
- `PROTECTED` - Protected access
- `INTERNAL` - Internal access (C#)
- `PROTECTED_INTERNAL` - Protected internal (C#)

## Parser Factory

The `ParserFactory` manages parser instances:

```python
from pathlib import Path
from src.parsers import ParserFactory

# Get parser by language
parser = ParserFactory.get_parser(LanguageEnum.TYPESCRIPT)

# Get parser by file extension
parser = ParserFactory.get_parser_for_file(Path("app.ts"))
```

## Language-Specific Features

### C# Parser

Extracts:
- Classes, interfaces, structs, enums
- Methods with parameters and return types
- Properties with types
- Fields (including multiple declarations)
- Access modifiers
- Using directives
- Documentation comments

### JavaScript Parser

Extracts:
- Function declarations
- Arrow functions
- ES6 classes
- Constructor and methods
- Import/export statements

### TypeScript Parser

Extends JavaScript parser with:
- Interface declarations
- Type aliases
- Enum declarations
- Type annotations

### Vue.js Parser

Extracts:
- Script section from Vue SFC
- Supports both `<script>` and `<script lang="ts">`
- Supports `<script setup>` syntax
- Delegates to JavaScript or TypeScript parser

## Error Handling

Parsers handle errors gracefully:

```python
result = parser.parse(code_with_errors)

if result.parse_errors:
    print(f"Parsing encountered errors: {result.parse_errors}")

# Symbols that were successfully parsed are still available
print(f"Extracted {len(result.symbols)} symbols despite errors")
```

## Performance

- Typical files (<1000 lines): < 1ms
- Timeout protection: 30 seconds (Unix only)
- Memory efficient: <500MB per parse
- Parser instances are cached

## Metrics

Parsers automatically record metrics:

```
parsing_duration_seconds{language="csharp"} 0.0007
parsing_duration_seconds{language="javascript"} 0.0004
```

## Testing

Run the unit tests:

```bash
pytest tests/unit/test_parsers.py -v
```

## Extending

To add a new language parser:

1. Install the tree-sitter language package
2. Create a new parser class extending `TreeSitterParser`
3. Implement `_extract_symbols()`, `_extract_imports()`, `_extract_exports()`
4. Add to `ParserFactory._create_parser()`
5. Add tests

Example:

```python
import tree_sitter_python
from src.parsers.tree_sitter_parser import TreeSitterParser

class PythonParser(TreeSitterParser):
    def __init__(self):
        super().__init__(LanguageEnum.PYTHON, tree_sitter_python)
    
    def is_supported(self, file_path: Path) -> bool:
        return file_path.suffix.lower() == '.py'
    
    def _extract_symbols(self, node, code):
        # Implementation here
        pass
```

## Troubleshooting

### Import Error

If you get `ModuleNotFoundError: No module named 'tree_sitter'`:

```bash
pip install tree-sitter tree-sitter-c-sharp tree-sitter-javascript tree-sitter-typescript
```

### Parse Timeout

On Windows, timeout protection is not enforced. For problematic files, consider:
- Pre-validating file size
- Using subprocess with timeout
- Implementing file size limits

### Low Accuracy

If symbol extraction accuracy is < 95%:
1. Check tree-sitter grammar version compatibility
2. Verify node types in AST (use tree-sitter playground)
3. Add more node type handlers in `_extract_symbols()`

## References

- [Tree-sitter Documentation](https://tree-sitter.github.io/tree-sitter/)
- [Tree-sitter Playground](https://tree-sitter.github.io/tree-sitter/playground)
- Task 05 Documentation: `docs/TASK_05_Code_Parsers.md`
- Implementation Summary: `docs/TASK_05_IMPLEMENTATION_COMPLETE.md`

