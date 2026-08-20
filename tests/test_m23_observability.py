import logging
import os
import importlib.util
import re
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from PyQt5.QtWidgets import QApplication, QMainWindow

from nanosense.core.acquisition import AcquisitionService
from nanosense.ml.lspr_ai_service import LSPRAIService
from nanosense.ml.lspr_backend_protocol import PredictionResponse
from nanosense.utils.logging_config import logging_context


_APP = QApplication.instance() or QApplication([])
HAS_PYTEST_QT = importlib.util.find_spec("pytestqt") is not None


class _Controller:
    def get_spectrum(self):
        return [500.0, 600.0], [1.0, 2.0]


class _Backend:
    def predict_single(self, request):
        return PredictionResponse(
            ok=True,
            backend="m23-test",
            model_mode="auto",
            predicted_concentration_ng_ml=1.0,
            report_mode="quantitative",
            reported_text="1.0 ng/ml",
            uloq_ng_ml=None,
            super_quant_bin=None,
            metrics={},
        )


def _wait_until(predicate, timeout_s=1.0):
    deadline = __import__("time").monotonic() + timeout_s
    while __import__("time").monotonic() < deadline:
        _APP.processEvents()
        if predicate():
            return True
        __import__("time").sleep(0.005)
    _APP.processEvents()
    return predicate()


def test_mock_acquisition_and_lspr_logs_share_session_and_use_operation_correlations(caplog):
    service = AcquisitionService(_Controller(), poll_interval_s=0.001)
    service._session_id = "m23-session"
    lspr = LSPRAIService(backend=_Backend())

    with logging_context(session_id="m23-session"):
        with caplog.at_level(logging.INFO):
            assert service.start() is True
            assert _wait_until(lambda: service.is_running)
            service.stop(timeout_s=1.0)
            lspr.predict_single_spectrum([500.0, 501.0, 502.0], [1.0, 2.0, 3.0])

    service.close(timeout_s=1.0)
    records = [
        record
        for record in caplog.records
        if record.name in {
            "nanosense.core.acquisition",
            "nanosense.ml.lspr_ai_service",
        }
    ]
    assert records
    assert {record.session_id for record in records} == {"m23-session"}
    acquisition_correlations = {
        record.correlation_id
        for record in records
        if record.name == "nanosense.core.acquisition"
    }
    lspr_correlations = {
        record.correlation_id
        for record in records
        if record.name == "nanosense.ml.lspr_ai_service"
    }
    assert len(acquisition_correlations) == 1
    assert next(iter(acquisition_correlations)).startswith("acq-")
    assert len(lspr_correlations) == 1
    assert lspr_correlations != acquisition_correlations


def test_application_sources_do_not_use_bare_except_handlers():
    root = Path(__file__).resolve().parents[1] / "nanosense"
    bare_handlers = []
    for path in root.rglob("*.py"):
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if re.match(r"^\s*except\s*:\s*$", line):
                bare_handlers.append(f"{path.relative_to(root.parent)}:{line_number}")

    assert bare_handlers == []


def test_three_file_theme_fallback_is_logged(caplog, monkeypatch):
    from nanosense.gui import three_file_import_dialog

    dialog = three_file_import_dialog.ThreeFileImportDialog()
    monkeypatch.setattr(
        three_file_import_dialog,
        "load_settings",
        lambda: (_ for _ in ()).throw(OSError("settings unavailable")),
    )

    with caplog.at_level(logging.WARNING, logger="nanosense.gui.three_file_import_dialog"):
        dialog._update_plot_styles()

    assert any("event=plot_theme_fallback" in record.getMessage() for record in caplog.records)
    dialog.close()


def test_analysis_theme_update_failure_is_logged(caplog, monkeypatch):
    from nanosense.gui import analysis_window

    window = analysis_window.AnalysisWindow([])
    monkeypatch.setattr(
        analysis_window,
        "load_settings",
        lambda: (_ for _ in ()).throw(OSError("settings unavailable")),
    )

    with caplog.at_level(logging.WARNING, logger="nanosense.gui.analysis_window"):
        window._update_plot_styles()

    assert any("event=analysis_plot_theme_update_failed" in record.getMessage() for record in caplog.records)
    monkeypatch.undo()
    window.close()


@pytest.mark.skipif(not HAS_PYTEST_QT, reason="pytest-qt is not installed")
def test_colorimetry_widget_reports_user_feedback_to_parent_status_bar(qtbot, monkeypatch):
    from nanosense.gui.colorimetry_widget import ColorimetryWidget

    window = QMainWindow()
    widget = ColorimetryWidget(parent=window)
    qtbot.addWidget(window)
    widget.wavelengths = np.array([500.0, 600.0])
    widget.spectral_data = np.array([1.0, 2.0])
    monkeypatch.setattr(
        "nanosense.gui.colorimetry_widget.calculate_colorimetric_values",
        lambda *args: {"X": 1.0},
    )

    widget._calculate_and_display_results()

    assert "Colorimetric parameters calculated" in window.statusBar().currentMessage()


@pytest.mark.skipif(not HAS_PYTEST_QT, reason="pytest-qt is not installed")
def test_summary_report_worker_emits_completion_signal(qtbot, tmp_path):
    from nanosense.gui.analysis_window import SummaryReportWorker

    spectra = {
        "sample": {
            "name": "sample",
            "x": np.linspace(500.0, 700.0, 11),
            "y": np.linspace(0.1, 0.2, 11),
        }
    }
    worker = SummaryReportWorker(
        spectra,
        str(tmp_path),
        apply_baseline=False,
        apply_smoothing=False,
        preprocessing_enabled=False,
        find_range=(500.0, 700.0),
        noise_range=(500.0, 510.0),
        peak_method="highest_point",
        min_height=0.0,
    )

    with qtbot.waitSignal(worker.finished, timeout=10000) as blocker:
        worker.start()

    assert blocker.args[0] == "success"
    worker.wait(1000)
