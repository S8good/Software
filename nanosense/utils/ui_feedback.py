from nanosense.utils.logging_config import get_logger


logger = get_logger(__name__)


def show_status_message(widget, message, timeout_ms=5000, event_logger=None):
    """Show transient user feedback in the owning Qt window and record it."""
    text = str(message)
    window = widget.window() if widget is not None else None
    status_bar_factory = getattr(window, "statusBar", None)
    if callable(status_bar_factory):
        status_bar_factory().showMessage(text, timeout_ms)

    (event_logger or logger).info("event=ui_status message=%s", text)
