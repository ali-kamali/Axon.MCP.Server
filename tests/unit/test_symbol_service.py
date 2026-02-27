from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.api.services.symbol_service import SymbolService
from src.config.enums import LanguageEnum, RelationTypeEnum, SymbolKindEnum
from src.database.models import File, Relation, Repository, Symbol


@pytest.mark.asyncio
async def test_get_symbol_normalizes_legacy_tuple_parameters():
    session = AsyncMock()

    symbol = Symbol(
        id=42,
        file_id=11,
        language=LanguageEnum.PYTHON,
        kind=SymbolKindEnum.FUNCTION,
        name="do_work",
        start_line=1,
        end_line=2,
        parameters=("repo", "limit"),
        created_at=datetime.now(UTC),
    )
    file = File(id=11, repository_id=7, path="src/tasks.py", language=LanguageEnum.PYTHON)
    repository = Repository(id=7, name="demo", path_with_namespace="org/demo")

    result = MagicMock()
    result.first.return_value = (symbol, file, repository)
    session.execute.return_value = result

    service = SymbolService(session)
    response = await service.get_symbol(42)

    assert response is not None
    assert response.parameters == {"param_0": "repo", "param_1": "limit"}


@pytest.mark.asyncio
async def test_get_symbol_with_relations_returns_ordered_edges():
    session = AsyncMock()

    base_symbol = Symbol(
        id=10,
        file_id=1,
        language=LanguageEnum.PYTHON,
        kind=SymbolKindEnum.FUNCTION,
        name="entrypoint",
        start_line=1,
        end_line=3,
        created_at=datetime.now(UTC),
    )
    file = File(id=1, repository_id=1, path="main.py", language=LanguageEnum.PYTHON)
    repository = Repository(id=1, name="demo", path_with_namespace="org/demo")

    symbol_result = MagicMock()
    symbol_result.first.return_value = (base_symbol, file, repository)

    rel_1 = Relation(
        id=2,
        from_symbol_id=10,
        to_symbol_id=13,
        relation_type=RelationTypeEnum.CALLS,
    )
    rel_2 = Relation(
        id=9,
        from_symbol_id=10,
        to_symbol_id=15,
        relation_type=RelationTypeEnum.REFERENCES,
    )

    target_a = Symbol(
        id=13,
        file_id=1,
        language=LanguageEnum.PYTHON,
        kind=SymbolKindEnum.FUNCTION,
        name="helper_a",
        start_line=5,
        end_line=6,
        created_at=datetime.now(UTC),
    )
    target_b = Symbol(
        id=15,
        file_id=1,
        language=LanguageEnum.PYTHON,
        kind=SymbolKindEnum.CLASS,
        name="HelperB",
        start_line=8,
        end_line=14,
        created_at=datetime.now(UTC),
    )

    relation_result = MagicMock()
    relation_result.all.return_value = [(rel_1, target_a), (rel_2, target_b)]

    session.execute.side_effect = [symbol_result, relation_result]

    service = SymbolService(session)
    response = await service.get_symbol_with_relations(10)

    assert response is not None
    assert [edge.id for edge in response.relations] == [2, 9]
    assert response.relations[0].to_symbol_name == "helper_a"
    assert response.relations[1].to_symbol_name == "HelperB"
