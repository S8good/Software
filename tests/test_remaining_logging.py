import logging
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
from PyQt5.QtWidgets import QApplication

from nanosense.algorithms.peak_analysis import find_spectral_peaks
from nanosense.algorithms.peak_analysis import calculate_sers_enhancement_factor
from nanosense.gui.analysis_window import AnalysisWindow
from nanosense.tools.lspr_export import LSPRDataExporter
from nanosense.utils.report_generator import run_analysis_pipeline


_APP = QApplication.instance() or QApplication([])


def test_algorithm_failure_uses_logger_without_console_output(caplog, capsys):
    with caplog.at_level(logging.ERROR, logger="nanosense.algorithms.peak_analysis"):
        indices, properties = find_spectral_peaks(None)

    assert indices.size == 0
    assert properties == {}
    assert any("event=peak_detection_failed" in record.getMessage() for record in caplog.records)
    assert capsys.readouterr().out == ""


def test_sers_validation_uses_logger_without_console_output(caplog, capsys):
    with caplog.at_level(logging.WARNING, logger="nanosense.algorithms.peak_analysis"):
        result = calculate_sers_enhancement_factor(None, np.array([1.0]), 1.0, 1.0)

    assert result is None
    assert any("event=sers_enhancement_rejected" in record.getMessage() for record in caplog.records)
    assert capsys.readouterr().out == ""


def test_report_pipeline_failure_uses_exception_logger(caplog, capsys):
    with caplog.at_level(logging.ERROR, logger="nanosense.utils.report_generator"):
        result = run_analysis_pipeline([500.0], None)

    assert "error" in result
    assert any("event=report_analysis_failed" in record.getMessage() for record in caplog.records)
    assert any(record.exc_info for record in caplog.records)
    assert capsys.readouterr().out == ""


def test_lspr_export_failure_uses_exception_logger(caplog, capsys, monkeypatch, tmp_path):
    exporter = LSPRDataExporter()

    def fail_open(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr("builtins.open", fail_open)
    with caplog.at_level(logging.ERROR, logger="nanosense.tools.lspr_export"):
        result = exporter.export_to_csv(
            str(tmp_path / "export.csv"), np.ones((2, 2)), {"size": 2}
        )

    assert result is False
    assert any("event=lspr_csv_export_failed" in record.getMessage() for record in caplog.records)
    assert any(record.exc_info for record in caplog.records)
    assert capsys.readouterr().out == ""


def test_analysis_window_user_feedback_uses_status_bar(caplog, capsys):
    window = AnalysisWindow([])

    with caplog.at_level(logging.INFO, logger="nanosense.gui.analysis_window"):
        window._reset_plot_view()

    assert "View reset" in window.statusBar().currentMessage()
    assert any("event=ui_status" in record.getMessage() for record in caplog.records)
    assert capsys.readouterr().out == ""

    window.close()
    _APP.processEvents()
