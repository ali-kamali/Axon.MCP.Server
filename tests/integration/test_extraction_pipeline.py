import pytest
from pathlib import Path
from sqlalchemy import select
from src.extractors.knowledge_extractor import KnowledgeExtractor
from src.database.session import get_async_session
from src.database.models import Repository, File, Symbol, Chunk, Relation
from src.config.enums import LanguageEnum, RepositoryStatusEnum, SymbolKindEnum, RelationTypeEnum
from src.parsers.base_parser import ParseResult, ParsedSymbol

@pytest.mark.asyncio
async def test_end_to_end_extraction(tmp_path):
    """Test complete extraction pipeline."""
    # Create a mock parse result
    class_symbol = ParsedSymbol(
        kind=SymbolKindEnum.CLASS,
        name="TestClass",
        start_line=1,
        end_line=10,
        start_column=0,
        end_column=0,
        signature="public class TestClass",
        documentation="Test class documentation",
        fully_qualified_name="TestNamespace.TestClass"
    )
    
    method_symbol = ParsedSymbol(
        kind=SymbolKindEnum.METHOD,
        name="TestMethod",
        start_line=3,
        end_line=8,
        start_column=4,
        end_column=4,
        signature="public void TestMethod()",
        documentation="Test method documentation",
        fully_qualified_name="TestNamespace.TestClass.TestMethod",
        parent_name="TestNamespace.TestClass"
    )
    
    parse_result = ParseResult(
        language=LanguageEnum.CSHARP,
        file_path="test.cs",
        symbols=[class_symbol, method_symbol],
        imports=[],
        exports=[],
        parse_errors=[],
        parse_duration_ms=100.0
    )
    
    # Extract knowledge
    async with get_async_session() as session:
        # Create repository and file records
        repo = Repository(
            gitlab_project_id=123,
            name="test-repo",
            path_with_namespace="test/repo",
            url="https://gitlab.com/test/repo",
            status=RepositoryStatusEnum.PARSING
        )
        session.add(repo)
        await session.flush()
        
        file_record = File(
            repository_id=repo.id,
            path="test.cs",
            language=LanguageEnum.CSHARP,
            size_bytes=100
        )
        session.add(file_record)
        await session.flush()
        
        # Extract and persist
        extractor = KnowledgeExtractor(session)
        result = await extractor.extract_and_persist(
            parse_result,
            file_record.id
        )
        
        # Verify extraction results
        assert result.symbols_created == 2
        assert result.chunks_created == 2
        assert result.relations_created == 1  # Parent-child relationship
        assert len(result.errors) == 0
        
        # Check database - symbols
        symbols_result = await session.execute(
            select(Symbol).where(Symbol.file_id == file_record.id)
        )
        symbols = symbols_result.scalars().all()
        
        assert len(symbols) == 2
        assert any(s.name == "TestClass" for s in symbols)
        assert any(s.name == "TestMethod" for s in symbols)
        
        # Check database - chunks
        chunks_result = await session.execute(
            select(Chunk).where(Chunk.file_id == file_record.id)
        )
        chunks = chunks_result.scalars().all()
        
        assert len(chunks) == 2
        assert all(c.content is not None for c in chunks)
        assert all(c.token_count > 0 for c in chunks)
        
        # Check database - relations
        relations_result = await session.execute(
            select(Relation).join(Symbol, Symbol.id == Relation.from_symbol_id)
            .where(Symbol.file_id == file_record.id)
        )
        relations = relations_result.scalars().all()
        
        assert len(relations) == 1
        assert relations[0].relation_type == RelationTypeEnum.CONTAINS

@pytest.mark.asyncio
async def test_extraction_with_multiple_files():
    """Test extraction across multiple files."""
    # Create mock parse results for two files
    file1_parse_result = ParseResult(
        language=LanguageEnum.CSHARP,
        file_path="file1.cs",
        symbols=[
            ParsedSymbol(
                kind=SymbolKindEnum.CLASS,
                name="BaseClass",
                start_line=1,
                end_line=10,
                start_column=0,
                end_column=0,
                signature="public class BaseClass",
                fully_qualified_name="MyNamespace.BaseClass"
            )
        ],
        imports=[],
        exports=[],
        parse_errors=[],
        parse_duration_ms=50.0
    )
    
    file2_parse_result = ParseResult(
        language=LanguageEnum.CSHARP,
        file_path="file2.cs",
        symbols=[
            ParsedSymbol(
                kind=SymbolKindEnum.CLASS,
                name="DerivedClass",
                start_line=1,
                end_line=15,
                start_column=0,
                end_column=0,
                signature="public class DerivedClass : BaseClass",
                fully_qualified_name="MyNamespace.DerivedClass"
            )
        ],
        imports=[],
        exports=[],
        parse_errors=[],
        parse_duration_ms=60.0
    )
    
    async with get_async_session() as session:
        # Create repository
        repo = Repository(
            gitlab_project_id=456,
            name="multi-file-repo",
            path_with_namespace="test/multi-file",
            url="https://gitlab.com/test/multi-file",
            status=RepositoryStatusEnum.PARSING
        )
        session.add(repo)
        await session.flush()
        
        # Create file records
        file1 = File(
            repository_id=repo.id,
            path="file1.cs",
            language=LanguageEnum.CSHARP,
            size_bytes=200
        )
        file2 = File(
            repository_id=repo.id,
            path="file2.cs",
            language=LanguageEnum.CSHARP,
            size_bytes=300
        )
        session.add(file1)
        session.add(file2)
        await session.flush()
        
        # Extract knowledge from both files
        extractor = KnowledgeExtractor(session)
        
        result1 = await extractor.extract_and_persist(file1_parse_result, file1.id)
        assert result1.symbols_created == 1
        
        result2 = await extractor.extract_and_persist(file2_parse_result, file2.id)
        assert result2.symbols_created == 1
        
        # Verify symbols from both files
        all_symbols_result = await session.execute(
            select(Symbol).join(File).where(File.repository_id == repo.id)
        )
        all_symbols = all_symbols_result.scalars().all()
        
        assert len(all_symbols) == 2
        assert any(s.name == "BaseClass" for s in all_symbols)
        assert any(s.name == "DerivedClass" for s in all_symbols)

@pytest.mark.asyncio
async def test_re_extraction_replaces_old_symbols():
    """Test that re-extracting a file replaces old symbols."""
    # First extraction
    parse_result_v1 = ParseResult(
        language=LanguageEnum.CSHARP,
        file_path="evolving.cs",
        symbols=[
            ParsedSymbol(
                kind=SymbolKindEnum.CLASS,
                name="OldClass",
                start_line=1,
                end_line=5,
                start_column=0,
                end_column=0,
                signature="public class OldClass",
                fully_qualified_name="MyNamespace.OldClass"
            )
        ],
        imports=[],
        exports=[],
        parse_errors=[],
        parse_duration_ms=50.0
    )
    
    # Second extraction (file changed)
    parse_result_v2 = ParseResult(
        language=LanguageEnum.CSHARP,
        file_path="evolving.cs",
        symbols=[
            ParsedSymbol(
                kind=SymbolKindEnum.CLASS,
                name="NewClass",
                start_line=1,
                end_line=10,
                start_column=0,
                end_column=0,
                signature="public class NewClass",
                fully_qualified_name="MyNamespace.NewClass"
            )
        ],
        imports=[],
        exports=[],
        parse_errors=[],
        parse_duration_ms=60.0
    )
    
    async with get_async_session() as session:
        # Create repository and file
        repo = Repository(
            gitlab_project_id=789,
            name="evolving-repo",
            path_with_namespace="test/evolving",
            url="https://gitlab.com/test/evolving",
            status=RepositoryStatusEnum.PARSING
        )
        session.add(repo)
        await session.flush()
        
        file_record = File(
            repository_id=repo.id,
            path="evolving.cs",
            language=LanguageEnum.CSHARP,
            size_bytes=150
        )
        session.add(file_record)
        await session.flush()
        
        # First extraction
        extractor = KnowledgeExtractor(session)
        result1 = await extractor.extract_and_persist(parse_result_v1, file_record.id)
        assert result1.symbols_created == 1
        
        # Verify old symbol exists
        symbols_v1 = await session.execute(
            select(Symbol).where(Symbol.file_id == file_record.id)
        )
        symbols_list_v1 = symbols_v1.scalars().all()
        assert len(symbols_list_v1) == 1
        assert symbols_list_v1[0].name == "OldClass"
        
        # Second extraction (should replace old symbols)
        result2 = await extractor.extract_and_persist(parse_result_v2, file_record.id)
        assert result2.symbols_created == 1
        
        # Verify only new symbol exists
        symbols_v2 = await session.execute(
            select(Symbol).where(Symbol.file_id == file_record.id)
        )
        symbols_list_v2 = symbols_v2.scalars().all()
        assert len(symbols_list_v2) == 1
        assert symbols_list_v2[0].name == "NewClass"
        assert not any(s.name == "OldClass" for s in symbols_list_v2)

