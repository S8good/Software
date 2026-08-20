import logging
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pandas as pd
from PyQt5.QtWidgets import QApplication

from nanosense.core.spectrum_processor import SpectrumProcessor
from nanosense.utils.data_processor import export_grouped_data


_APP = QApplication.instance() or QApplication([])


def test_spectrum_processor_state_changes_are_logged(caplog, capsys):
    processor = SpectrumProcessor(np.array([500.0, 600.0, 700.0]))

    with caplog.at_level(logging.INFO, logger="nanosense.core.spectrum_processor"):
        processor.set_smoothing_params("No Smoothing", 5, 2)
        processor.set_baseline_params(True, algorithm="ALS", lam=100.0, p=0.1, niter=2)
        processor.set_analysis_range(510.0, 690.0)
        processor.set_mode("Raman")
        processor.set_background_from_spectrum(np.array([1.0, 1.0, 1.0]))
        processor.set_reference_from_spectrum(np.array([2.0, 2.0, 2.0]))

    messages = [record.getMessage() for record in caplog.records]
    assert any("event=spectrum_smoothing_updated" in message for message in messages)
    assert any("event=spectrum_baseline_updated" in message for message in messages)
    assert any("event=spectrum_range_updated" in message for message in messages)
    assert any("event=spectrum_mode_updated" in message for message in messages)
    assert any("event=spectrum_background_updated" in message for message in messages)
    assert any("event=spectrum_reference_updated" in message for message in messages)
    assert capsys.readouterr().out == ""


def test_grouped_export_failure_is_logged(caplog, monkeypatch, tmp_path):
    def fail_to_excel(self, *args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(pd.DataFrame, "to_excel", fail_to_excel)
    grouped_data = {"Point 1": pd.DataFrame({"Wavelength": [500.0], "run": [1.0]})}

    with caplog.at_level(logging.INFO, logger="nanosense.utils.data_processor"):
        exported = export_grouped_data(str(tmp_path), grouped_data, ["Point 1"])

    assert exported == []
    assert any(
        "event=grouped_export_failed" in record.getMessage()
        and "point=Point 1" in record.getMessage()
        for record in caplog.records
    )
