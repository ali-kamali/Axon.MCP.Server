import pytest
from unittest.mock import AsyncMock, MagicMock
from src.extractors.relationship_builder import RelationshipBuilder
from src.database.models import Symbol, Relation, File
from src.config.enums import SymbolKindEnum, RelationTypeEnum, LanguageEnum

@pytest.fixture
def mock_session():
    """Mock database session."""
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.add = MagicMock()
    # Mock flush to be async
    session.flush = AsyncMock()
    return session

@pytest.mark.asyncio
async def test_build_uses_relationships_di(mock_session):
    """Test building USES relationships from DI registrations."""
    # 1. Define Symbols
    # Service Interface
    service_interface = Symbol(
        id=1,
        file_id=1,
        language=LanguageEnum.CSHARP,
        kind=SymbolKindEnum.INTERFACE,
        name="IService",
        fully_qualified_name="MyNamespace.IService",
        structured_docs={}
    )
    
    # Implementation Class
    service_impl = Symbol(
        id=2,
        file_id=2,
        language=LanguageEnum.CSHARP,
        kind=SymbolKindEnum.CLASS,
        name="Service",
        fully_qualified_name="MyNamespace.Service",
        structured_docs={}
    )
    
    # Startup/Config Class that registers DI
    startup_class = Symbol(
        id=3,
        file_id=3,
        language=LanguageEnum.CSHARP,
        kind=SymbolKindEnum.CLASS,
        name="Startup",
        fully_qualified_name="MyNamespace.Startup",
        structured_docs={
            'references': [
                {'type': 'di_registration', 'name': 'IService', 'line': 10},
                {'type': 'di_registration', 'name': 'Service', 'line': 10}
            ]
        }
    )

    # 2. Mock Database Query
    mock_result = MagicMock()
    # Return all symbols so the builder indexes them
    mock_result.scalars().all.return_value = [service_interface, service_impl, startup_class]
    mock_session.execute.return_value = mock_result
    
    # 3. Method under test
    builder = RelationshipBuilder(mock_session)
    count = await builder.build_cross_file_relationships(repository_id=1)
    
    # 4. Verify
    # We expect relationships:
    # Startup -> IService (USES)
    # Startup -> Service (USES)
    # And potentially REFERENCES if fallback logic picks anything up, but here mainly USES
    
    # Filter for USES relations added to session
    uses_relations = []
    for call in mock_session.add.call_args_list:
        obj = call[0][0]
        if isinstance(obj, Relation) and obj.relation_type == RelationTypeEnum.USES:
            uses_relations.append(obj)
            
    assert len(uses_relations) == 2
    
    # Verify Startup uses IService
    uses_interface = next((r for r in uses_relations if r.to_symbol_id == 1), None)
    assert uses_interface is not None
    assert uses_interface.from_symbol_id == 3
    
    # Verify Startup uses Service
    uses_impl = next((r for r in uses_relations if r.to_symbol_id == 2), None)
    assert uses_impl is not None
    assert uses_impl.from_symbol_id == 3


@pytest.mark.asyncio
async def test_build_references_relationships_rich(mock_session):
    """Test building REFERENCES relationships from rich parser data (instantiations, variable types)."""
    # 1. Define Symbols
    target_class = Symbol(
        id=10,
        file_id=1,
        language=LanguageEnum.CSHARP,
        kind=SymbolKindEnum.CLASS,
        name="TargetClass",
        fully_qualified_name="MyNamespace.TargetClass",
        structured_docs={}
    )
    
    consumer_class = Symbol(
        id=11,
        file_id=2,
        language=LanguageEnum.CSHARP,
        kind=SymbolKindEnum.CLASS,
        name="Consumer",
        fully_qualified_name="MyNamespace.Consumer",
        structured_docs={
            'references': [
                {'type': 'instantiation', 'name': 'TargetClass', 'line': 20},
                {'type': 'type_reference', 'name': 'TargetClass', 'line': 25} # Variable usage
            ]
        }
    )

    # 2. Mock Database Query
    mock_result = MagicMock()
    mock_result.scalars().all.return_value = [target_class, consumer_class]
    mock_session.execute.return_value = mock_result
    
    # 3. Method under test
    builder = RelationshipBuilder(mock_session)
    count = await builder.build_cross_file_relationships(repository_id=1)
    
    # 4. Verify
    # We expect Consumer -> TargetClass (REFERENCES)
    
    ref_relations = []
    for call in mock_session.add.call_args_list:
        obj = call[0][0]
        if isinstance(obj, Relation) and obj.relation_type == RelationTypeEnum.REFERENCES:
            ref_relations.append(obj)
            
    # Should find at least one (deduplicated logic might make it 1 even if 2 refs exist)
    assert len(ref_relations) >= 1
    
    relation = next((r for r in ref_relations if r.to_symbol_id == 10), None)
    assert relation is not None
    assert relation.from_symbol_id == 11
