import threading
import time

import numpy as np
import pytest
from PyQt5.QtCore import QCoreApplication

from nanosense.core.acquisition import AcquisitionService, AcquisitionState


@pytest.fixture(scope="session")
def qt_app():
    app = QCoreApplication.instance() or QCoreApplication([])
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


def _wait_until(predicate, timeout=1.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app = QCoreApplication.instance()
        if app is not None:
            app.processEvents()
        if predicate():
            return True
        time.sleep(0.005)
    app = QCoreApplication.instance()
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


def test_one_hundred_start_stop_cycles_leave_no_thread(qt_app):
    service = AcquisitionService(_StableController(), poll_interval_s=0.0)
    for _ in range(100):
        assert service.start() is True
        assert service.stop(timeout_s=1.0) is True
    assert not service.is_running
    assert service.thread is None or not service.thread.is_alive()
    service.close(timeout_s=1.0)
