import logging
from types import SimpleNamespace

from nanosense.gui.main_window import AppWindow


class _Event:
    def __init__(self):
        self.accepted = False

    def accept(self):
        self.accepted = True


def test_close_event_logs_shutdown_lifecycle(caplog):
    calls = []
    fake_window = SimpleNamespace(
        measurement_page=SimpleNamespace(
            stop_all_activities=lambda: calls.append("measurement_stop")
        ),
        batch_service=SimpleNamespace(
            close=lambda timeout_s: calls.append(("batch_close", timeout_s))
        ),
        db_manager=SimpleNamespace(close=lambda: calls.append("database_close")),
    )
    event = _Event()

    with caplog.at_level(logging.INFO, logger="nanosense.gui.main_window"):
        AppWindow.closeEvent(fake_window, event)

    assert event.accepted is True
    assert calls == ["measurement_stop", ("batch_close", 2.0), "database_close"]
    messages = [record.getMessage() for record in caplog.records]
    assert any("event=application_shutdown_started" in message for message in messages)
    assert any("event=database_closed" in message for message in messages)
    assert any("event=application_shutdown_completed" in message for message in messages)
