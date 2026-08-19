import threading
from enum import Enum

import numpy as np
from PyQt5.QtCore import QObject, pyqtSignal


class AcquisitionState(str, Enum):
    IDLE = "idle"
    CONNECTING = "connecting"
    READY = "ready"
    ACQUIRING = "acquiring"
    STOPPING = "stopping"
    ERROR = "error"


class AcquisitionService(QObject):
    state_changed = pyqtSignal(object)
    spectrum_ready = pyqtSignal(object, object)
    error_occurred = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(
        self,
        controller=None,
        *,
        poll_interval_s=0.1,
        error_backoff_s=0.05,
        max_consecutive_errors=3,
        release_callback=None,
        parent=None,
    ):
        super().__init__(parent)
        self.controller = controller
        self.poll_interval_s = max(0.0, float(poll_interval_s))
        self.error_backoff_s = max(0.0, float(error_backoff_s))
        self.max_consecutive_errors = max(1, int(max_consecutive_errors))
        self.release_callback = release_callback
        self._state = AcquisitionState.IDLE
        self._thread = None
        self._stop_event = threading.Event()
        self._lock = threading.RLock()
        self._closed = False

    @property
    def state(self):
        return self._state

    @property
    def thread(self):
        return self._thread

    @property
    def is_running(self):
        return self._thread is not None and self._thread.is_alive()

    def _set_state(self, state):
        with self._lock:
            if self._state is state:
                return
            self._state = state
        self.state_changed.emit(state)

    def start(self):
        with self._lock:
            if self._closed:
                return False
            if self.is_running or self._state in (
                AcquisitionState.READY,
                AcquisitionState.ACQUIRING,
                AcquisitionState.STOPPING,
            ):
                return True
            if self._state is AcquisitionState.ERROR:
                return False
            self._stop_event.clear()
            self._set_state(AcquisitionState.CONNECTING)
            self._thread = threading.Thread(
                target=self._run,
                name="nanosense-acquisition",
                daemon=True,
            )
            thread = self._thread
            thread.start()
            self._set_state(AcquisitionState.READY)
            self._set_state(AcquisitionState.ACQUIRING)
            return True

    def _run(self):
        consecutive_errors = 0
        try:
            while not self._stop_event.is_set():
                if self.controller is None:
                    raise RuntimeError("No acquisition controller is configured")
                try:
                    wavelengths, spectrum = self.controller.get_spectrum()
                    consecutive_errors = 0
                    self.spectrum_ready.emit(
                        np.asarray(wavelengths), np.asarray(spectrum)
                    )
                    if self.poll_interval_s:
                        self._stop_event.wait(self.poll_interval_s)
                except Exception as exc:
                    consecutive_errors += 1
                    if consecutive_errors >= self.max_consecutive_errors:
                        self.error_occurred.emit(str(exc))
                        self._set_state(AcquisitionState.ERROR)
                        break
                    if self.error_backoff_s:
                        self._stop_event.wait(self.error_backoff_s)
        except Exception as exc:
            self.error_occurred.emit(str(exc))
            self._set_state(AcquisitionState.ERROR)
        finally:
            self.finished.emit()

    def wait(self, timeout_s=0.5):
        thread = self._thread
        if thread is None:
            return True
        thread.join(max(0.0, float(timeout_s)))
        return not thread.is_alive()

    def _stop_single(self, timeout_s=0.5):
        with self._lock:
            if not self.is_running:
                if self._state is AcquisitionState.STOPPING:
                    self._set_state(AcquisitionState.IDLE)
                return True
            self._set_state(AcquisitionState.STOPPING)
            self._stop_event.set()
        stopped = self.wait(timeout_s)
        if stopped:
            self._set_state(AcquisitionState.IDLE)
            return True
        self.error_occurred.emit("Acquisition thread did not stop within the timeout")
        self._set_state(AcquisitionState.ERROR)
        return False

    def stop(self, timeout_s=0.5):
        return self._stop_single(timeout_s)

    def reset(self):
        with self._lock:
            if self.is_running:
                return False
            self._closed = False
            self._stop_event.clear()
            self._set_state(AcquisitionState.IDLE)
            return True

    def close(self, timeout_s=0.5):
        stopped = self.stop(timeout_s)
        with self._lock:
            self._closed = True
        if self.release_callback is not None:
            self.release_callback()
        return stopped

    @staticmethod
    def run_compat_loop(
        controller,
        stop_event,
        is_active,
        emit,
        error_backoff_s,
        idle_sleep_s,
    ):
        while not stop_event.is_set():
            if controller is None or not is_active():
                stop_event.wait(idle_sleep_s)
                continue
            try:
                _, spectrum = controller.get_spectrum()
                emit(spectrum)
            except Exception:
                stop_event.wait(error_backoff_s)
