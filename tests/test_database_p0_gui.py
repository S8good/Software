import numpy as np

from nanosense.core.spectrum_processor import SpectrumProcessor
from nanosense.gui.measurement_widget import MeasurementWidget


def test_measurement_widget_exposes_method_controls_and_qc_summary(qtbot):
    processor = SpectrumProcessor(np.array([400.0, 401.0, 402.0]))
    widget = MeasurementWidget(None, processor)
    qtbot.addWidget(widget)

    assert hasattr(widget, "processing_method_combo")
    assert hasattr(widget, "save_processing_method_button")
    assert hasattr(widget, "quality_summary_label")

    widget._on_result_updated(
        np.array([400.0, 401.0, 402.0]),
        np.array([0.1, np.nan, 0.3]),
    )

    assert "fail" in widget.quality_summary_label.text().lower()


def test_database_explorer_exposes_reanalysis_action(qtbot):
    from nanosense.gui.database_explorer import DatabaseExplorerDialog

    dialog = DatabaseExplorerDialog()
    qtbot.addWidget(dialog)

    assert hasattr(dialog, "reanalysis_button")
    assert hasattr(dialog, "reanalysis_requested")
