import contextlib
import contextvars
import logging
import logging.handlers
import secrets
import sys
from pathlib import Path


DEFAULT_MAX_BYTES = 5 * 1024 * 1024
DEFAULT_BACKUP_COUNT = 3
_session_id = contextvars.ContextVar("nanosense_session_id", default="-")
_correlation_id = contextvars.ContextVar("nanosense_correlation_id", default="-")
_HANDLER_MARKER = "_nanosense_handler"


def new_session_id(prefix="session"):
    return f"{prefix}-{secrets.token_hex(6)}"


def new_correlation_id(prefix="task"):
    return f"{prefix}-{secrets.token_hex(6)}"


def current_context():
    return {"session_id": _session_id.get(), "correlation_id": _correlation_id.get()}


@contextlib.contextmanager
def logging_context(session_id=None, correlation_id=None):
    session_token = None
    correlation_token = None
    if session_id is not None:
        session_token = _session_id.set(str(session_id))
    if correlation_id is not None:
        correlation_token = _correlation_id.set(str(correlation_id))
    try:
        yield current_context()
    finally:
        if correlation_token is not None:
            _correlation_id.reset(correlation_token)
        if session_token is not None:
            _session_id.reset(session_token)


class ContextFilter(logging.Filter):
    def filter(self, record):
        context = current_context()
        record.session_id = context["session_id"]
        record.correlation_id = context["correlation_id"]
        return True


def get_logger(name):
    return logging.getLogger(name)


def configure_logging(log_dir=None, level=logging.INFO, reset=False):
    target_dir = (
        Path(log_dir)
        if log_dir is not None
        else Path(__file__).resolve().parents[2] / "logs"
    )
    target_dir.mkdir(parents=True, exist_ok=True)
    log_path = target_dir / "nanosense.log"
    root = logging.getLogger()
    root.setLevel(level)

    marked_handlers = [
        handler
        for handler in root.handlers
        if getattr(handler, _HANDLER_MARKER, False)
    ]
    if reset:
        for handler in marked_handlers:
            root.removeHandler(handler)
            handler.close()
        marked_handlers = []
    if marked_handlers:
        return log_path

    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s "
        "session=%(session_id)s correlation=%(correlation_id)s %(message)s"
    )
    context_filter = ContextFilter()
    console = logging.StreamHandler(sys.stderr)
    console.setFormatter(formatter)
    console.addFilter(context_filter)
    setattr(console, _HANDLER_MARKER, True)
    file_handler = logging.handlers.RotatingFileHandler(
        log_path,
        maxBytes=DEFAULT_MAX_BYTES,
        backupCount=DEFAULT_BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.addFilter(context_filter)
    setattr(file_handler, _HANDLER_MARKER, True)
    root.addHandler(console)
    root.addHandler(file_handler)
    return log_path
