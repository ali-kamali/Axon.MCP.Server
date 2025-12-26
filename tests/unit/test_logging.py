from src.utils.logging_config import configure_logging, get_logger


def test_logger_initialization() -> None:
    """Test logger can be initialized."""
    configure_logging()
    logger = get_logger("test")
    assert logger is not None


def test_structured_logging() -> None:
    """Test structured logging output (no exceptions)."""
    configure_logging()
    logger = get_logger("test")

    # Should not raise
    logger.info("test_event", key1="value1", key2=123)
    logger.error("test_error", error="something went wrong")


