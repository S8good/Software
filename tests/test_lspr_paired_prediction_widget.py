import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication

from nanosense.gui.lspr_paired_prediction_widget import LSPRPairedPredictionWidget
from nanosense.ml.lspr_ai_service import LSPRAIService


_APP = QApplication.instance() or QApplication([])


def _load_pair(widget, analyte_id="cea"):
    wavelengths = [500.0, 600.0, 700.0]
    widget.set_paired_spectra(
        wavelengths,
        [1.0, 2.0, 1.5],
        wavelengths,
        [1.1, 2.2, 1.4],
        chip_id="chip-01",
        site_id="site-01",
        analyte_id=analyte_id,
    )


def test_workbench_requires_a_pair_and_shows_model_state():
    service = LSPRAIService(backend=object())
    widget = LSPRPairedPredictionWidget(lambda: service)
    try:
        assert widget.predict_button.isEnabled() is False
        _load_pair(widget, analyte_id="cea")
        assert "Pair valid" in widget.validation_status_label.text()
        assert "artifact" in widget.model_status_label.text().lower()
        assert widget.predict_button.isEnabled() is False
    finally:
        widget.close()


def test_planned_analyte_is_registered_but_cannot_predict():
    service = LSPRAIService(backend=object())
    widget = LSPRPairedPredictionWidget(lambda: service)
    try:
        assert widget.set_analyte("nse") is True
        _load_pair(widget, analyte_id="nse")
        assert "Pair valid" in widget.validation_status_label.text()
        assert "not supplied" in widget.model_status_label.text().lower()
        assert widget.predict_button.isEnabled() is False
        assert widget._last_result is None
    finally:
        widget.close()
