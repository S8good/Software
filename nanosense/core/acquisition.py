import threading
from enum import Enum

import numpy as np
from PyQt5.QtCore import QObject, QThread, Qt, pyqtSignal

from nanosense.utils.logging_config import (
    current_context,
    get_logger,
    logging_context,
    new_correlation_id,
)


logger = get_logger(__name__)


def _context_extra(session_id, correlation_id):
    return {"session_id": session_id, "correlation_id": correlation_id}


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
        self._released = False
        self._batch_handle = None
        self._session_id = "-"
        self._correlation_id = None

    @property
    def state(self):
        return self._state

    @property
    def thread(self):
        return self._thread

    @property
    def is_running(self):
        return (
            self._thread is not None and self._thread.is_alive()
        ) or (
            self._batch_handle is not None
            and self._batch_handle.thread.isRunning()
        )

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
            self._session_id = current_context()["session_id"]
            self._correlation_id = new_correlation_id("acq")
            with logging_context(
                session_id=self._session_id,
                correlation_id=self._correlation_id,
            ):
                logger.info(
                    "acquisition_started event=acquisition_started",
                    extra=_context_extra(self._session_id, self._correlation_id),
                )
            self._set_state(AcquisitionState.CONNECTING)
            self._thread = threading.Thread(
                target=self._run,
                name="nanosense-acquisition",
                daemon=True,
            )
            thread = self._thread
            self._set_state(AcquisitionState.READY)
            self._set_state(AcquisitionState.ACQUIRING)
            thread.start()
            return True

    def _run(self):
        consecutive_errors = 0
        with logging_context(
            session_id=self._session_id,
            correlation_id=self._correlation_id,
        ):
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
                            logger.exception(
                                "acquisition_failed event=acquisition_failed",
                                extra=_context_extra(
                                    self._session_id, self._correlation_id
                                ),
                            )
                            self.error_occurred.emit(str(exc))
                            self._set_state(AcquisitionState.ERROR)
                            break
                        if self.error_backoff_s:
                            self._stop_event.wait(self.error_backoff_s)
            except Exception as exc:
                logger.exception(
                    "acquisition_failed event=acquisition_failed",
                    extra=_context_extra(self._session_id, self._correlation_id),
                )
                self.error_occurred.emit(str(exc))
                self._set_state(AcquisitionState.ERROR)
            finally:
                logger.info(
                    "acquisition_finished event=acquisition_finished",
                    extra=_context_extra(self._session_id, self._correlation_id),
                )
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
            with logging_context(
                session_id=self._session_id,
                correlation_id=self._correlation_id,
            ):
                logger.info(
                    "acquisition_stop_requested event=acquisition_stop_requested",
                    extra=_context_extra(self._session_id, self._correlation_id),
                )
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
        handle = self._batch_handle
        if handle is not None and handle.thread.isRunning():
            return handle.close(timeout_ms=max(0, int(float(timeout_s) * 1000)))
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
            should_release = stopped and not self._released
            if should_release:
                self._released = True
        if self.release_callback is not None and should_release:
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

    def start_batch(self, worker):
        with self._lock:
            if self._closed or self.is_running:
                return self._batch_handle
            self._session_id = current_context()["session_id"]
            self._correlation_id = new_correlation_id("batch")
            with logging_context(
                session_id=self._session_id,
                correlation_id=self._correlation_id,
            ):
                logger.info(
                    "batch_started event=batch_started",
                    extra=_context_extra(self._session_id, self._correlation_id),
                )
            self._set_state(AcquisitionState.CONNECTING)
            self._batch_handle = BatchAcquisitionHandle(worker, parent=self)
            self._batch_handle.state_changed.connect(
                self._set_state, Qt.DirectConnection
            )
            self._batch_handle.error_occurred.connect(
                self.error_occurred.emit, Qt.DirectConnection
            )
            self._batch_handle.finished.connect(
                self._on_batch_finished, Qt.DirectConnection
            )
            self._batch_handle.start()
            return self._batch_handle

    def _on_batch_finished(self):
        handle = self._batch_handle
        if handle is None:
            return
        if getattr(handle.worker, "run_status", None) == "failed":
            self._set_state(AcquisitionState.ERROR)
        elif self._state is not AcquisitionState.ERROR:
            self._set_state(AcquisitionState.IDLE)
        with logging_context(
            session_id=self._session_id,
            correlation_id=self._correlation_id,
        ):
            logger.info(
                "batch_finished event=batch_finished status=%s",
                getattr(handle.worker, "run_status", "unknown"),
                extra=_context_extra(self._session_id, self._correlation_id),
            )
        self.finished.emit()


class BatchAcquisitionHandle(QObject):
    state_changed = pyqtSignal(object)
    error_occurred = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(self, worker, parent=None):
        super().__init__(parent)
        self.worker = worker
        self.thread = QThread()
        self._state = AcquisitionState.IDLE
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.thread.quit, Qt.DirectConnection)
        self.worker.finished.connect(self._on_worker_finished, Qt.DirectConnection)
        self.worker.error.connect(self.error_occurred.emit)
        self.thread.finished.connect(self._on_thread_finished, Qt.DirectConnection)

    @property
    def state(self):
        return self._state

    def _set_state(self, state):
        if self._state is state:
            return
        self._state = state
        self.state_changed.emit(state)

    def start(self):
        if self.thread.isRunning():
            return True
        self._set_state(AcquisitionState.CONNECTING)
        self.thread.start()
        self._set_state(AcquisitionState.ACQUIRING)
        return True

    def stop(self):
        if not self.thread.isRunning():
            return True
        self._set_state(AcquisitionState.STOPPING)
        self.worker.stop()
        return True

    def wait(self, timeout_ms=500):
        if not self.thread.isRunning():
            return True
        return bool(self.thread.wait(max(0, int(timeout_ms))))

    def close(self, timeout_ms=500):
        self.stop()
        stopped = self.wait(timeout_ms)
        if not stopped:
            self._set_state(AcquisitionState.ERROR)
            self.error_occurred.emit(
                "Batch acquisition thread did not stop within the timeout"
            )
        return stopped

    def _on_worker_finished(self):
        if getattr(self.worker, "run_status", None) == "failed":
            self._set_state(AcquisitionState.ERROR)
        elif self._state is not AcquisitionState.STOPPING:
            self._set_state(AcquisitionState.READY)

    def _on_thread_finished(self):
        if self._state is AcquisitionState.STOPPING:
            self._set_state(AcquisitionState.IDLE)
        self.finished.emit()
