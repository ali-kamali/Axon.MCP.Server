import pytest

from src.utils.metrics import (
    api_requests_total,
    parsing_duration,
    increment_counter,
    track_time,
)


@pytest.mark.asyncio
async def test_track_time_decorator() -> None:
    """Test track_time decorator."""

    @track_time(parsing_duration, {"language": "test"})
    async def sample_function() -> str:
        return "success"

    result = await sample_function()
    assert result == "success"


def test_increment_counter_decorator() -> None:
    """Test increment_counter decorator."""

    @increment_counter(api_requests_total, {"method": "GET", "endpoint": "/test", "status": "200"})
    def sample_function() -> str:
        return "success"

    result = sample_function()
    assert result == "success"


