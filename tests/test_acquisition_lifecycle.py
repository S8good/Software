import os
import threading
import time
from pathlib import Path

import numpy as np
import pytest
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot
from PyQt5.QtWidgets import QApplication

from nanosense.core.acquisition import AcquisitionService, AcquisitionState


@pytest.fixture(scope="session")
def qt_app():
    app = QApplication.instance() or QApplication([])
    return app


class _StableController:
    wavelengths = np.array([500.0, 600.0, 700.0])

    def __init__(self):
        self.calls = 0

    def get_spectrum(self):
        self.calls += 1
        return self.wavelengths, np.array([1.0, 2.0, 3.0])


class _FatalController:
    wavelengths = np.array([500.0, 600.0, 700.0])

    def get_spectrum(self):
        raise RuntimeError("device disconnected")


class _BlockingController:
    wavelengths = np.array([500.0, 600.0, 700.0])

    def __init__(self):
        self.entered = threading.Event()
        self.release = threading.Event()

    def get_spectrum(self):
        self.entered.set()
        self.release.wait(1.0)
        return self.wavelengths, np.array([1.0, 2.0, 3.0])


def _wait_until(predicate, timeout=1.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app = QApplication.instance()
        if app is not None:
            app.processEvents()
        if predicate():
            return True
        time.sleep(0.005)
    app = QApplication.instance()
    if app is not None:
        app.processEvents()
    return predicate()


def test_service_emits_ready_acquiring_and_idle_states(qt_app):
    service = AcquisitionService(_StableController(), poll_interval_s=0.001)
    states = []
    spectra = []
    service.state_changed.connect(states.append)
    service.spectrum_ready.connect(lambda x, y: spectra.append((x, y)))

    assert service.start() is True
    assert _wait_until(lambda: bool(spectra))
    assert service.stop(timeout_s=1.0) is True

    assert states[0] is AcquisitionState.CONNECTING
    assert AcquisitionState.READY in states
    assert AcquisitionState.ACQUIRING in states
    assert states[-1] is AcquisitionState.IDLE
    assert not service.is_running
    service.close(timeout_s=1.0)


def test_start_stop_and_close_are_idempotent(qt_app):
    service = AcquisitionService(_StableController(), poll_interval_s=0.001)
    assert service.start() is True
    assert service.start() is True
    assert service.stop(timeout_s=1.0) is True
    assert service.stop(timeout_s=1.0) is True
    assert service.close(timeout_s=1.0) is True
    assert service.close(timeout_s=1.0) is True


def test_fatal_device_errors_reach_error_state(qt_app):
    service = AcquisitionService(
        _FatalController(),
        poll_interval_s=0.001,
        error_backoff_s=0.001,
        max_consecutive_errors=2,
    )
    errors = []
    service.error_occurred.connect(errors.append)

    assert service.start() is True
    assert _wait_until(lambda: service.state is AcquisitionState.ERROR)
    assert errors == ["device disconnected"]
    assert service.stop(timeout_s=1.0) is True
    service.close(timeout_s=1.0)


def test_close_releases_once_and_not_before_a_timeout_is_recovered(qt_app):
    controller = _BlockingController()
    released = []
    service = AcquisitionService(
        controller,
        poll_interval_s=0.0,
        release_callback=lambda: released.append(True),
    )
    assert service.start() is True
    assert _wait_until(controller.entered.is_set)
    assert service.stop(timeout_s=0.01) is False
    assert released == []

    controller.release.set()
    assert service.stop(timeout_s=1.0) is True
    assert service.close(timeout_s=1.0) is True
    assert service.close(timeout_s=1.0) is True
    assert released == [True]


def test_one_hundred_start_stop_cycles_leave_no_thread(qt_app):
    service = AcquisitionService(_StableController(), poll_interval_s=0.0)
    for _ in range(100):
        assert service.start() is True
        assert service.stop(timeout_s=1.0) is True
    assert not service.is_running
    assert service.thread is None or not service.thread.is_alive()
    service.close(timeout_s=1.0)


class _FakeBatchWorker(QObject):
    finished = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.run_status = "pending"
        self.stop_calls = 0

    @pyqtSlot()
    def run(self):
        time.sleep(0.02)
        self.run_status = "completed"
        self.finished.emit()

    @pyqtSlot()
    def stop(self):
        self.stop_calls += 1
        self.run_status = "aborted"
        self.finished.emit()


def test_batch_handle_owns_thread_and_close_is_idempotent(qt_app):
    service = AcquisitionService()
    worker = _FakeBatchWorker()
    handle = service.start_batch(worker)

    assert handle.thread.isRunning()
    assert handle.wait(timeout_ms=1000) is True
    assert worker.run_status == "completed"
    assert service.state is AcquisitionState.IDLE
    assert service.close(timeout_s=1.0) is True
    assert service.close(timeout_s=1.0) is True


def test_measurement_widget_stop_all_activities_delegates_to_service():
    calls = []
    fake = type("Widget", (), {})()
    fake.is_kinetics_monitoring = False
    fake.is_acquiring = True
    fake.acquisition_service = type(
        "Service", (), {"close": lambda self, timeout_s=0.5: calls.append(timeout_s)}
    )()
    fake._refresh_raman_workflow = lambda: None

    from nanosense.gui.measurement_widget import MeasurementWidget

    MeasurementWidget.stop_all_activities(fake)
    assert calls == [0.5]


def test_main_window_does_not_create_or_wait_on_batch_threads():
    source = Path("nanosense/gui/main_window.py").read_text(encoding="utf-8")
    assert "self.batch_thread = QThread()" not in source
    assert "self.batch_worker.moveToThread" not in source
    assert "self.batch_thread.start()" not in source
    assert "self.batch_thread.wait" not in source


def test_main_window_wires_batch_signals_before_starting_service():
    source = Path("nanosense/gui/main_window.py").read_text(encoding="utf-8")
    start_index = source.index("self.batch_handle = self.batch_service.start_batch")
    preview_index = source.index("self.batch_worker.update_dialog.connect")
    peak_index = source.index("self.batch_worker.peak_found.connect")
    assert start_index > preview_index
    assert start_index > peak_index
