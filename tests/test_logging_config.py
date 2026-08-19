import logging
import logging.handlers

from nanosense.utils.logging_config import (
    configure_logging,
    current_context,
    get_logger,
    logging_context,
    new_correlation_id,
    new_session_id,
)


def test_configure_logging_is_idempotent_and_writes_context(tmp_path):
    log_path = configure_logging(tmp_path, level=logging.INFO, reset=True)
    handler_count = len(logging.getLogger().handlers)
    assert configure_logging(tmp_path, level=logging.INFO) == log_path
    assert len(logging.getLogger().handlers) == handler_count

    logger = get_logger("tests.logging")
    session_id = new_session_id()
    correlation_id = new_correlation_id("acq")
    with logging_context(session_id=session_id, correlation_id=correlation_id):
        logger.info("acquisition_started event=acquisition_started")

    text = log_path.read_text(encoding="utf-8")
    assert session_id in text
    assert correlation_id in text
    assert "event=acquisition_started" in text


def test_context_is_nested_and_restored():
    outer = current_context()
    with logging_context(session_id="session-a", correlation_id="task-a"):
        assert current_context() == {
            "session_id": "session-a",
            "correlation_id": "task-a",
        }
        with logging_context(correlation_id="task-b"):
            assert current_context() == {
                "session_id": "session-a",
                "correlation_id": "task-b",
            }
        assert current_context()["correlation_id"] == "task-a"
    assert current_context() == outer


def test_exception_logging_keeps_traceback_without_sensitive_payload(tmp_path):
    log_path = configure_logging(tmp_path, level=logging.INFO, reset=True)
    logger = get_logger("tests.exception")
    secret = "PRIVATE-CONFIG-VALUE"
    try:
        raise ValueError("simulated backend failure")
    except ValueError:
        logger.exception("backend_failed event=backend_failed")

    text = log_path.read_text(encoding="utf-8")
    assert "ValueError: simulated backend failure" in text
    assert "Traceback (most recent call last)" in text
    assert secret not in text


def test_file_handler_uses_rotation(tmp_path):
    log_path = configure_logging(tmp_path, level=logging.INFO, reset=True)
    root = logging.getLogger()
    rotating = [
        handler for handler in root.handlers
        if isinstance(handler, logging.handlers.RotatingFileHandler)
    ]
    assert log_path.name == "nanosense.log"
    assert rotating
    assert rotating[0].maxBytes == 5 * 1024 * 1024
    assert rotating[0].backupCount == 3
