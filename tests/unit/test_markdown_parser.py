"""Tests for markdown parser."""

import pytest
from src.parsers.markdown_parser import MarkdownParser
from src.config.enums import SymbolKindEnum


class TestMarkdownParser:
    """Test markdown parser functionality."""
    
    def setup_method(self):
        """Setup test fixtures."""
        self.parser = MarkdownParser()
    
    def test_parse_headings(self):
        """Test that headings are extracted as document sections."""
        markdown = """# Main Title
        
Some content here.

## Section 1

Content for section 1.

### Subsection 1.1

More content.
"""
        result = self.parser.parse(markdown, "README.md")
        
        assert result.language.value == "markdown"
        assert len(result.symbols) > 0
        
        # Check for headings
        headings = [s for s in result.symbols if s.kind == SymbolKindEnum.DOCUMENT_SECTION]
        assert len(headings) == 3
        
        # Check main title
        main_title = headings[0]
        assert main_title.name == "Main Title"
        assert main_title.structured_docs['level'] == 1
    
    def test_parse_code_blocks(self):
        """Test that code blocks are extracted."""
        markdown = """# Example

Here's some Python code:

```python
def hello():
    print("Hello, World!")
```

And some JavaScript:

```javascript
function greet() {
    console.log("Hello!");
}
```
"""
        result = self.parser.parse(markdown, "guide.md")
        
        # Check for code examples
        code_examples = [s for s in result.symbols if s.kind == SymbolKindEnum.CODE_EXAMPLE]
        assert len(code_examples) == 2
        
        # Check Python example
        python_example = code_examples[0]
        assert python_example.structured_docs['language'] == 'python'
        assert 'def hello()' in python_example.documentation
        
        # Check JavaScript example
        js_example = code_examples[1]
        assert js_example.structured_docs['language'] == 'javascript'
    
    def test_extract_links(self):
        """Test that markdown links are extracted."""
        markdown = """# Documentation

See [API Reference](./api.md) for details.

Also check out [GitHub](https://github.com/example/repo).
"""
        result = self.parser.parse(markdown, "docs.md")
        
        # Links are stored in imports
        assert len(result.imports) > 0
        assert './api.md' in result.imports or 'https://github.com/example/repo' in result.imports
    
    def test_empty_markdown(self):
        """Test parsing empty markdown."""
        result = self.parser.parse("", "empty.md")
        
        assert result.language.value == "markdown"
        assert len(result.symbols) == 0
        assert len(result.parse_errors) == 0
    
    def test_nested_headings(self):
        """Test deeply nested heading structure."""
        markdown = """# Level 1
## Level 2
### Level 3
#### Level 4
##### Level 5
###### Level 6
"""
        result = self.parser.parse(markdown, "nested.md")
        
        headings = [s for s in result.symbols if s.kind == SymbolKindEnum.DOCUMENT_SECTION]
        assert len(headings) == 6
        
        # Verify levels
        for i, heading in enumerate(headings, start=1):
            assert heading.structured_docs['level'] == i

