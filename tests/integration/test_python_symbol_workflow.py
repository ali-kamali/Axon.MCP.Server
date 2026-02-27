from pathlib import Path

import pytest
from sqlalchemy import select

from src.api.services.symbol_service import SymbolService
from src.config.enums import LanguageEnum, RepositoryStatusEnum
from src.database.models import File, Repository, Symbol
from src.parsers import ParserFactory


@pytest.mark.asyncio
async def test_python_symbols_are_discoverable_after_ingestion(async_session):
    parser = ParserFactory.get_parser_for_file(Path("service.py"))
    code = """
class UserService:
    def get_user(self, user_id: int) -> dict:
        return {"id": user_id}

def compute_score(value: int) -> int:
    return value * 2
"""

    parsed = parser.parse(code, "service.py")
    assert parsed.symbols, "parser should extract python symbols"

    repo = Repository(
        gitlab_project_id=501,
        name="python-repo",
        path_with_namespace="demo/python-repo",
        url="https://example.com/demo/python-repo.git",
        clone_url="https://example.com/demo/python-repo.git",
        default_branch="main",
        status=RepositoryStatusEnum.PENDING,
    )
    async_session.add(repo)
    await async_session.flush()

    file = File(path="service.py", repository_id=repo.id, language=LanguageEnum.PYTHON)
    async_session.add(file)
    await async_session.flush()

    for item in parsed.symbols:
        async_session.add(
            Symbol(
                file_id=file.id,
                language=item.language,
                kind=item.kind,
                access_modifier=item.access_modifier,
                name=item.name,
                fully_qualified_name=item.fully_qualified_name,
                start_line=item.start_line,
                end_line=item.end_line,
                signature=item.signature,
                documentation=item.documentation,
                parameters=item.parameters,
                return_type=item.return_type,
                parent_name=item.parent_name,
            )
        )

    await async_session.commit()

    stored_symbol = (
        await async_session.execute(
            select(Symbol)
            .join(File, Symbol.file_id == File.id)
            .where(File.repository_id == repo.id, Symbol.name == "compute_score")
        )
    ).scalar_one()

    service = SymbolService(async_session)
    response = await service.get_symbol(stored_symbol.id)

    assert response is not None
    assert response.name == "compute_score"
    assert response.language == LanguageEnum.PYTHON
    assert response.file_id == file.id
