# Acquisition Service Boundary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将单次和批量采集的线程生命周期、停止等待和资源释放收敛到 `AcquisitionService`，让 GUI 只负责控制和显示。

**Architecture:** `nanosense/core/acquisition.py` 提供统一状态枚举、单次采集服务和 `BatchAcquisitionHandle`。单次服务拥有 Python 采集线程；批量句柄拥有 `QThread`，但复用现有 `BatchAcquisitionWorker` 的业务循环。`MeasurementWidget` 和 `MainWindow` 只调用服务 API、连接 Qt signal，不再创建、join 或直接管理采集线程。

**Tech Stack:** Python 3.9, PyQt5 signals/QThread, `threading.Event`/`RLock`, pytest, NumPy。

---

### Task 1: Define and test the continuous acquisition lifecycle

**Files:**
- Create: `tests/test_acquisition_lifecycle.py`
- Modify: `nanosense/core/acquisition.py`

- [ ] **Step 1: Write the failing lifecycle tests**

Add the following imports, fixtures, fake controllers, and tests to `tests/test_acquisition_lifecycle.py`:

```python
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
        if predicate():
            return True
        time.sleep(0.005)
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
```

- [ ] **Step 2: Run the new tests to verify RED**

Run:

```powershell
C:\ProgramData\anaconda3\envs\py39\python.exe -m pytest tests/test_acquisition_lifecycle.py -q
```

Expected: collection fails with `ImportError` because `AcquisitionService` and `AcquisitionState` do not yet exist.

- [ ] **Step 3: Implement the minimal continuous service**

Replace the comment-only `nanosense/core/acquisition.py` with this implementation:

```python
import threading
import time
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
```

- [ ] **Step 4: Run the focused tests to verify GREEN**

Run:

```powershell
C:\ProgramData\anaconda3\envs\py39\python.exe -m pytest tests/test_acquisition_lifecycle.py -q
```

Expected: `4 passed`.

- [ ] **Step 5: Commit the core service**

```powershell
git add nanosense/core/acquisition.py tests/test_acquisition_lifecycle.py
git commit -m "feat: add acquisition lifecycle service"
```

### Task 2: Add a service-owned batch QThread handle

**Files:**
- Modify: `tests/test_acquisition_lifecycle.py`
- Modify: `nanosense/core/acquisition.py`

- [ ] **Step 1: Add a failing batch ownership test**

Append the following fake worker and test:

```python
from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot


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
```

- [ ] **Step 2: Run the batch test to verify RED**

Run:

```powershell
C:\ProgramData\anaconda3\envs\py39\python.exe -m pytest tests/test_acquisition_lifecycle.py::test_batch_handle_owns_thread_and_close_is_idempotent -q
```

Expected: `AttributeError: 'AcquisitionService' object has no attribute 'start_batch'`.

- [ ] **Step 3: Implement `BatchAcquisitionHandle` and `start_batch()`**

Add the following `BatchAcquisitionHandle` class below `AcquisitionService` in `nanosense/core/acquisition.py`. The handle owns the `QThread`; the service only keeps the active handle and maps its terminal state. Add `self._batch_handle = None` in `AcquisitionService.__init__`, add the shown `start_batch` and `_on_batch_finished` methods inside the class, and update `stop` to delegate to the active batch handle before handling the single-acquisition thread.

```python
from PyQt5.QtCore import QThread


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
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self._on_worker_finished)
        self.worker.error.connect(self.error_occurred.emit)
        self.thread.finished.connect(self._on_thread_finished)

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
            self.error_occurred.emit("Batch acquisition thread did not stop within the timeout")
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


    def start_batch(self, worker):
        with self._lock:
            if self._closed or self.is_running:
                return self._batch_handle
            self._set_state(AcquisitionState.CONNECTING)
            self._batch_handle = BatchAcquisitionHandle(worker, parent=self)
            self._batch_handle.state_changed.connect(self._set_state)
            self._batch_handle.error_occurred.connect(self.error_occurred.emit)
            self._batch_handle.finished.connect(self._on_batch_finished)
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
        self.finished.emit()

    def stop(self, timeout_s=0.5):
        handle = self._batch_handle
        if handle is not None and handle.thread.isRunning():
            return handle.close(timeout_ms=max(0, int(float(timeout_s) * 1000)))
        return self._stop_single(timeout_s)
```

The implementation must initialize `self._batch_handle = None` in `AcquisitionService.__init__` and place `start_batch`, `_on_batch_finished`, and the batch-aware `stop` directly in the class. The snippet shows the complete signatures and behavior required by the tests.

- [ ] **Step 4: Run focused tests to verify GREEN**

```powershell
C:\ProgramData\anaconda3\envs\py39\python.exe -m pytest tests/test_acquisition_lifecycle.py -q
```

Expected: `5 passed`.

- [ ] **Step 5: Commit batch ownership**

```powershell
git add nanosense/core/acquisition.py tests/test_acquisition_lifecycle.py
git commit -m "feat: own batch acquisition thread in service"
```

### Task 3: Move MeasurementWidget control to AcquisitionService

**Files:**
- Modify: `nanosense/gui/measurement_widget.py`
- Modify: `tests/test_acquisition_lifecycle.py`

- [ ] **Step 1: Add a failing widget delegation test**

Append this test using a small fake widget object:

```python
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
```

- [ ] **Step 2: Run the widget test to verify RED**

```powershell
C:\ProgramData\anaconda3\envs\py39\python.exe -m pytest tests/test_acquisition_lifecycle.py::test_measurement_widget_stop_all_activities_delegates_to_service -q
```

Expected: failure because `stop_all_activities` still accesses `stop_event` and `acquisition_thread` instead of delegating to `acquisition_service`.

- [ ] **Step 3: Replace direct thread ownership in `MeasurementWidget`**

In `__init__`, replace `stop_event` and `acquisition_thread` construction with:

```python
from nanosense.core.acquisition import AcquisitionService, AcquisitionState

self.acquisition_service = AcquisitionService(self.controller, parent=self)
self.acquisition_service.spectrum_ready.connect(self._on_service_spectrum_ready)
self.acquisition_service.state_changed.connect(self._on_acquisition_state_changed)
self.acquisition_service.error_occurred.connect(self._on_acquisition_error)
self.acquisition_service.finished.connect(self._on_acquisition_finished)
```

Add the main-thread slots:

```python
def _on_service_spectrum_ready(self, wavelengths, spectrum):
    if self.data_queue.full():
        try:
            self.data_queue.get_nowait()
        except queue.Empty:
            pass
    self.data_queue.put(np.asarray(spectrum))

def _on_acquisition_state_changed(self, state):
    self.is_acquiring = state in (
        AcquisitionState.CONNECTING,
        AcquisitionState.READY,
        AcquisitionState.ACQUIRING,
        AcquisitionState.STOPPING,
    )
    if hasattr(self, "toggle_acq_button"):
        self.toggle_acq_button.setChecked(self.is_acquiring)
        self.toggle_acq_button.setText(
            self.tr("Stop Acquisition") if self.is_acquiring else self.tr("Start Acquisition")
        )
    self._refresh_raman_workflow()

def _on_acquisition_error(self, message):
    self._last_acquisition_error_message = message
    print(self.tr("Acquisition error: {0}").format(message))

def _on_acquisition_finished(self):
    if hasattr(self, "update_timer") and not self.is_acquiring:
        self.update_timer.stop()
```

Replace `_toggle_acquisition` with service calls:

```python
def _toggle_acquisition(self, start):
    if start:
        started = self.acquisition_service.start()
        if started:
            self.last_result_processing_time = None
            if not hasattr(self, "update_timer"):
                self.update_timer = QTimer(self)
                self.update_timer.setInterval(50)
                self.update_timer.timeout.connect(self.update_plot)
            self.update_timer.start()
    else:
        self.acquisition_service.stop(timeout_s=0.5)
        if hasattr(self, "update_timer"):
            self.update_timer.stop()
    self._refresh_raman_workflow()
```

Replace `acquisition_thread_func` with a compatibility adapter that preserves the existing recovery test without creating a thread in the widget:

```python
def acquisition_thread_func(self):
    AcquisitionService.run_compat_loop(
        controller=self.controller,
        stop_event=self.stop_event,
        is_active=lambda: self.is_acquiring,
        emit=lambda spectrum: self.data_queue.put(np.asarray(spectrum)),
        error_backoff_s=getattr(self, "acquisition_error_backoff_s", 0.05),
        idle_sleep_s=getattr(self, "acquisition_idle_sleep_s", 0.1),
    )
```

Add this static helper to `AcquisitionService`; it is used only by the legacy recovery test adapter, while production starts acquisition through `start()`:

```python
    @staticmethod
    def run_compat_loop(controller, stop_event, is_active, emit, error_backoff_s, idle_sleep_s):
        repeat_count = 0
        while not stop_event.is_set():
            if controller is None or not is_active():
                stop_event.wait(idle_sleep_s)
                continue
            try:
                _, spectrum = controller.get_spectrum()
                repeat_count = 0
                emit(spectrum)
            except Exception:
                repeat_count += 1
                stop_event.wait(error_backoff_s)
```

Rewrite `stop_all_activities` as:

```python
def stop_all_activities(self):
    if self.is_kinetics_monitoring:
        self._toggle_kinetics_window()
    if hasattr(self, "acquisition_service"):
        self.acquisition_service.close(timeout_s=0.5)
    self.is_acquiring = False
```

Move the retry loop used by `run_compat_loop` out of the widget and keep its existing behavior: one failed read sleeps, a later successful read is emitted, and the loop exits when `stop_event` is set.

- [ ] **Step 4: Run focused and regression tests**

```powershell
C:\ProgramData\anaconda3\envs\py39\python.exe -m pytest tests/test_acquisition_lifecycle.py tests/test_ocean_acquisition_recovery.py -q
```

Expected: all tests pass, including the existing flaky Ocean recovery test.

- [ ] **Step 5: Commit the measurement integration**

```powershell
git add nanosense/gui/measurement_widget.py nanosense/core/acquisition.py tests/test_acquisition_lifecycle.py
git commit -m "refactor: delegate measurement lifecycle to service"
```

### Task 4: Move MainWindow batch thread ownership to the service

**Files:**
- Modify: `nanosense/gui/main_window.py`
- Modify: `nanosense/core/acquisition.py`
- Modify: `tests/test_acquisition_lifecycle.py`

- [ ] **Step 1: Add a failing source-level ownership test**

Add this narrow contract test for the main-window close path:

```python
def test_main_window_does_not_create_or_wait_on_batch_threads():
    from pathlib import Path

    source = Path("nanosense/gui/main_window.py").read_text(encoding="utf-8")
    assert "self.batch_thread = QThread()" not in source
    assert "self.batch_worker.moveToThread" not in source
    assert "self.batch_thread.start()" not in source
    assert "self.batch_thread.wait" not in source
```

- [ ] **Step 2: Run the test to verify RED**

```powershell
C:\ProgramData\anaconda3\envs\py39\python.exe -m pytest tests/test_acquisition_lifecycle.py::test_batch_service_close_waits_for_worker_thread -q
```

Expected: failure because the current `MainWindow` directly creates and starts `QThread`.

- [ ] **Step 3: Update MainWindow to call the service**

Import `AcquisitionService` and replace the direct thread construction in the batch-start method:

```python
self.batch_service = AcquisitionService(self.controller, parent=self)
        self.batch_worker = BatchAcquisitionWorker(
            self.controller,
            layout_data,
            output_folder,
            file_extension,
            points_per_well=points_per_well,
            crop_start_wl=crop_start,
            crop_end_wl=crop_end,
            is_auto_enabled=is_auto_enabled,
            intra_well_interval=intra_well_interval,
            inter_well_interval=inter_well_interval,
            db_manager=self.db_manager,
            project_id=self.current_project_id,
            operator=operator_name,
            instrument_info=instrument_info,
            processing_info=processing_info,
            peak_method=self.run_dialog.get_selected_peak_method(),
            processing_settings=self.run_dialog.processing_settings.copy(),
        )
self.batch_handle = self.batch_service.start_batch(self.batch_worker)
self.batch_thread = self.batch_handle.thread

self.batch_worker.error.connect(self._show_batch_error)
self.batch_worker.update_dialog.connect(self.run_dialog.update_state)
self.batch_worker.live_preview_data.connect(self.run_dialog.update_all_plots)
self.batch_worker.peak_found.connect(self.run_dialog.update_peak_table)
self.batch_worker.peak_removed.connect(self.run_dialog.remove_from_peak_table)
```

Keep the existing dialog-to-worker command connections, but remove all GUI-owned `QThread` setup and teardown connections (`moveToThread`, `started`, `finished.connect(thread.quit)`, `deleteLater`, and `thread.start`). Add a helper:

```python
def _show_batch_error(self, message):
    QMessageBox.critical(self, self.tr("Error"), self.tr(message))
```

In `closeEvent` and `_abort_batch_task`, replace direct `worker.stop()`, `thread.quit()` and `thread.wait()` calls with:

```python
service = getattr(self, "batch_service", None)
if service is not None:
    service.close(timeout_s=2.0)
```

Retain `self.batch_thread = self.batch_handle.thread` only as a compatibility reference for existing code/tests; no method in `MainWindow` may call `start`, `quit`, `wait`, or `deleteLater` on it. Keep `_on_batch_acquisition_finished` reading `batch_worker.run_status` and clearing `batch_service`, `batch_handle`, `batch_worker`, and `batch_thread` after the dialog closes.

- [ ] **Step 4: Run batch and GUI import tests**

```powershell
C:\ProgramData\anaconda3\envs\py39\python.exe -m pytest tests/test_acquisition_lifecycle.py tests/test_main_window_imports.py tests/test_batch_preview.py tests/test_database_manager_batch.py -q
```

Expected: all selected tests pass and no GUI thread-lifecycle assertion fails.

- [ ] **Step 5: Commit the MainWindow integration**

```powershell
git add nanosense/gui/main_window.py nanosense/core/acquisition.py tests/test_acquisition_lifecycle.py
git commit -m "refactor: centralize batch thread lifecycle"
```

### Task 5: Full verification and cleanup

**Files:**
- Modify: `tests/test_acquisition_lifecycle.py` if a deterministic race exposed by the full suite requires test synchronization.

- [ ] **Step 1: Run the complete test suite**

```powershell
C:\ProgramData\anaconda3\envs\py39\python.exe -m pytest -q
```

Expected: all existing tests plus the lifecycle tests pass with zero failures.

- [ ] **Step 2: Run dependency, bytecode, and diff checks**

```powershell
C:\ProgramData\anaconda3\envs\py39\python.exe -m pip check
C:\ProgramData\anaconda3\envs\py39\python.exe -m compileall -q nanosense tests
git diff --check
git status --short
```

Expected: `pip check` reports no broken requirements, `compileall` is silent, `git diff --check` is silent, and only intentional committed changes remain.

- [ ] **Step 3: Commit any final test-only synchronization fix**

If Step 2 found a deterministic test race, add the smallest synchronization change and run the complete suite again:

```powershell
git add tests/test_acquisition_lifecycle.py
git commit -m "test: stabilize acquisition lifecycle timing"
```
