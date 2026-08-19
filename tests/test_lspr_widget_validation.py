import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication, QMessageBox

from nanosense.gui.lspr_batch_prediction_widget import LSPRBatchPredictionWidget
from nanosense.ml.lspr_ai_service import LSPRAIServiceError


_APP = None


def qapp():
    global _APP
    if _APP is None:
        _APP = QApplication.instance() or QApplication([])
    return _APP


def test_batch_widget_shows_safe_error_and_keeps_table_empty(monkeypatch):
    qapp()
    messages = []

    class FailingService:
        def predict_batch(self, items, model_mode="auto"):
            raise LSPRAIServiceError(
                "model_error",
                "Model inference failed.",
                {"traceback": "SECRET_INTERNAL_TRACEBACK"},
            )

    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda parent, title, message: messages.append((title, message)),
    )
    widget = LSPRBatchPredictionWidget(lambda: FailingService())
    widget._items = [
        {
            "label": "sample_1",
            "wavelengths": [500.0, 501.0, 502.0],
            "intensities": [0.1, 0.2, 0.3],
        }
    ]

    try:
        widget._run_batch_prediction()

        assert widget.results_table.rowCount() == 0
        assert messages
        assert messages[0][1] == "Model inference failed."
        assert "SECRET_INTERNAL_TRACEBACK" not in messages[0][1]
    finally:
        widget.close()
