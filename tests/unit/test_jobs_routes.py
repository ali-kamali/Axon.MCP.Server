from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from src.api.routes.jobs import (
    LinkMicroservicesRequest,
    trigger_link_microservices,
    trigger_link_repository,
)


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


@pytest.mark.asyncio
async def test_trigger_link_microservices_deduplicates_repository_ids():
    request = LinkMicroservicesRequest(repository_ids=[1, 2, 1, 3, 2])

    with patch("src.workers.tasks.link_microservices.delay") as mock_delay:
        mock_delay.return_value = SimpleNamespace(id="task-123")

        response = await trigger_link_microservices(request=request)

    mock_delay.assert_called_once_with(repository_ids=[1, 2, 3])
    assert response["task_id"] == "task-123"
    assert response["repository_ids"] == [1, 2, 3]


def test_link_microservices_request_rejects_non_positive_repository_ids():
    with pytest.raises(ValidationError, match="positive integers"):
        LinkMicroservicesRequest(repository_ids=[1, 0, -5])


@pytest.mark.asyncio
async def test_trigger_link_repository_returns_404_when_repository_missing():
    session = AsyncMock()
    session.execute = AsyncMock(return_value=_ScalarResult(None))

    with pytest.raises(HTTPException) as exc_info:
        await trigger_link_repository(repository_id=999, session=session)

    assert exc_info.value.status_code == 404
    assert "not found" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_trigger_link_repository_enqueues_task_for_existing_repository():
    session = AsyncMock()
    session.execute = AsyncMock(return_value=_ScalarResult(SimpleNamespace(name="repo-a")))

    with patch("src.workers.tasks.link_repository.delay") as mock_delay:
        mock_delay.return_value = SimpleNamespace(id="task-456")

        response = await trigger_link_repository(repository_id=7, session=session)

    mock_delay.assert_called_once_with(repository_id=7)
    assert response == {
        "message": "Linking task started for repository repo-a",
        "task_id": "task-456",
        "repository_id": 7,
        "repository_name": "repo-a",
        "status": "pending",
    }
