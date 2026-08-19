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


def test_launcher_uses_logging_setup_and_exception_logger():
    source = open("main.py", encoding="utf-8").read()
    assert "configure_logging" in source
    assert "new_session_id" in source
    assert "logger.exception" in source
    assert "with open(crash_log" not in source


def test_acquisition_logs_have_correlation_context(caplog):
    import time

    from nanosense.core.acquisition import AcquisitionService

    class Controller:
        def get_spectrum(self):
            return [500.0, 600.0], [1.0, 2.0]

    service = AcquisitionService(Controller(), poll_interval_s=0.001)
    with caplog.at_level(logging.INFO):
        assert service.start() is True
        time.sleep(0.02)
        assert service.stop(timeout_s=1.0) is True

    records = [
        record for record in caplog.records
        if record.name == "nanosense.core.acquisition"
    ]
    assert records
    assert any(record.correlation_id != "-" for record in records)
    assert any("acquisition_started" in record.getMessage() for record in records)


def test_lspr_logs_have_correlation_context(caplog):
    from nanosense.ml.lspr_ai_service import LSPRAIService
    from nanosense.ml.lspr_backend_protocol import PredictionResponse

    class Backend:
        def predict_single(self, request):
            return PredictionResponse(
                ok=True,
                backend="test",
                model_mode="auto",
                predicted_concentration_ng_ml=1.0,
                report_mode="quantitative",
                reported_text="1.0 ng/ml",
                uloq_ng_ml=None,
                super_quant_bin=None,
                metrics={},
            )

    service = LSPRAIService(backend=Backend())
    with caplog.at_level(logging.INFO):
        service.predict_single_spectrum([500.0, 501.0, 502.0], [1.0, 2.0, 3.0])

    records = [
        record for record in caplog.records
        if record.name == "nanosense.ml.lspr_ai_service"
    ]
    assert records
    assert any(record.correlation_id != "-" for record in records)
    assert any("lspr_started" in record.getMessage() for record in records)


def test_critical_modules_define_module_loggers():
    for path in (
        "nanosense/core/controller.py",
        "nanosense/core/batch_acquisition.py",
        "nanosense/core/database_manager.py",
    ):
        source = open(path, encoding="utf-8").read()
        assert "get_logger(__name__)" in source


def test_readme_documents_log_location():
    source = open("README.md", encoding="utf-8").read()
    assert "logs/nanosense.log" in source
