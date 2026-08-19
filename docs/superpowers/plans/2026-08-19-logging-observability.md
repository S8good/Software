# Unified Logging Observability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 NanoSense 建立带 session/correlation 上下文、控制台与滚动文件输出、关键采集/LSPR/数据库事件和敏感数据保护的统一日志系统。

**Architecture:** `nanosense/utils/logging_config.py` 使用标准库 `logging`、`contextvars` 和 `RotatingFileHandler`，为每条记录注入 session/correlation 字段。`main.py` 初始化 session；采集服务和 LSPR 任务创建 correlation；关键模块通过模块 logger 记录事件，GUI 文案和业务错误传播保持不变。

**Tech Stack:** Python 3.9 standard library logging/contextvars/secrets, PyQt5, pytest `caplog`, RotatingFileHandler。

---

### Task 1: Build and test the logging configuration module

**Files:**
- Create: `nanosense/utils/logging_config.py`
- Create: `tests/test_logging_config.py`

- [ ] **Step 1: Write failing configuration tests**

Create `tests/test_logging_config.py`:

```python
import logging
import re
import traceback

from nanosense.utils.logging_config import (
    configure_logging,
    current_context,
    get_logger,
    logging_context,
    new_correlation_id,
    new_session_id,
)


def test_configure_logging_is_idempotent_and_writes_context(tmp_path, caplog):
    log_path = configure_logging(tmp_path, level=logging.INFO, reset=True)
    handler_count = len(logging.getLogger().handlers)
    assert configure_logging(tmp_path, level=logging.INFO) == log_path
    assert len(logging.getLogger().handlers) == handler_count

    logger = get_logger("tests.logging")
    session_id = new_session_id()
    correlation_id = new_correlation_id("acq")
    with logging_context(session_id=session_id, correlation_id=correlation_id):
        logger.info("acquisition_started event=acquisition_started")

    text = log_path.read_text(encoding="utf-8")
    assert session_id in text
    assert correlation_id in text
    assert "event=acquisition_started" in text


def test_context_is_nested_and_restored():
    outer = current_context()
    with logging_context(session_id="session-a", correlation_id="task-a"):
        assert current_context() == {
            "session_id": "session-a",
            "correlation_id": "task-a",
        }
        with logging_context(correlation_id="task-b"):
            assert current_context() == {
                "session_id": "session-a",
                "correlation_id": "task-b",
            }
        assert current_context()["correlation_id"] == "task-a"
    assert current_context() == outer


def test_exception_logging_keeps_traceback_without_sensitive_payload(tmp_path):
    log_path = configure_logging(tmp_path, level=logging.INFO, reset=True)
    logger = get_logger("tests.exception")
    secret = "PRIVATE-CONFIG-VALUE"
    try:
        raise ValueError("simulated backend failure")
    except ValueError:
        logger.exception("backend_failed event=backend_failed")

    text = log_path.read_text(encoding="utf-8")
    assert "ValueError: simulated backend failure" in text
    assert "Traceback (most recent call last)" in text
    assert secret not in text
    assert not re.search(r"C:\\Users\\[^ ]+", text)


def test_file_handler_uses_rotation(tmp_path):
    log_path = configure_logging(tmp_path, level=logging.INFO, reset=True)
    root = logging.getLogger()
    rotating = [
        handler for handler in root.handlers
        if isinstance(handler, logging.handlers.RotatingFileHandler)
    ]
    assert log_path.name == "nanosense.log"
    assert rotating
    assert rotating[0].maxBytes == 5 * 1024 * 1024
    assert rotating[0].backupCount == 3
```

- [ ] **Step 2: Run tests to verify RED**

```powershell
C:\ProgramData\anaconda3\envs\py39\python.exe -m pytest tests/test_logging_config.py -q
```

Expected: collection fails with `ModuleNotFoundError` because `logging_config.py` does not exist.

- [ ] **Step 3: Implement the minimal logging configuration**

Create `nanosense/utils/logging_config.py`:

```python
import contextlib
import contextvars
import logging
import logging.handlers
import secrets
import sys
from pathlib import Path


DEFAULT_MAX_BYTES = 5 * 1024 * 1024
DEFAULT_BACKUP_COUNT = 3
_session_id = contextvars.ContextVar("nanosense_session_id", default="-")
_correlation_id = contextvars.ContextVar("nanosense_correlation_id", default="-")
_HANDLER_MARKER = "_nanosense_handler"


def new_session_id(prefix="session"):
    return f"{prefix}-{secrets.token_hex(6)}"


def new_correlation_id(prefix="task"):
    return f"{prefix}-{secrets.token_hex(6)}"


def current_context():
    return {"session_id": _session_id.get(), "correlation_id": _correlation_id.get()}


@contextlib.contextmanager
def logging_context(session_id=None, correlation_id=None):
    session_token = None
    correlation_token = None
    if session_id is not None:
        session_token = _session_id.set(str(session_id))
    if correlation_id is not None:
        correlation_token = _correlation_id.set(str(correlation_id))
    try:
        yield current_context()
    finally:
        if correlation_token is not None:
            _correlation_id.reset(correlation_token)
        if session_token is not None:
            _session_id.reset(session_token)


class ContextFilter(logging.Filter):
    def filter(self, record):
        context = current_context()
        record.session_id = context["session_id"]
        record.correlation_id = context["correlation_id"]
        return True


def get_logger(name):
    return logging.getLogger(name)


def configure_logging(log_dir=None, level=logging.INFO, reset=False):
    target_dir = Path(log_dir) if log_dir is not None else Path(__file__).resolve().parents[2] / "logs"
    target_dir.mkdir(parents=True, exist_ok=True)
    log_path = target_dir / "nanosense.log"
    root = logging.getLogger()
    root.setLevel(level)

    marked_handlers = [
        handler for handler in root.handlers
        if getattr(handler, _HANDLER_MARKER, False)
    ]
    if reset:
        for handler in marked_handlers:
            root.removeHandler(handler)
            handler.close()
        marked_handlers = []
    if marked_handlers:
        return log_path

    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s "
        "session=%(session_id)s correlation=%(correlation_id)s %(message)s"
    )
    context_filter = ContextFilter()
    console = logging.StreamHandler(sys.stderr)
    console.setFormatter(formatter)
    console.addFilter(context_filter)
    setattr(console, _HANDLER_MARKER, True)
    file_handler = logging.handlers.RotatingFileHandler(
        log_path,
        maxBytes=DEFAULT_MAX_BYTES,
        backupCount=DEFAULT_BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.addFilter(context_filter)
    setattr(file_handler, _HANDLER_MARKER, True)
    root.addHandler(console)
    root.addHandler(file_handler)
    return log_path
```

- [ ] **Step 4: Run focused tests to verify GREEN**

```powershell
C:\ProgramData\anaconda3\envs\py39\python.exe -m pytest tests/test_logging_config.py -q
```

Expected: `4 passed`.

- [ ] **Step 5: Commit the logging foundation**

```powershell
git add nanosense/utils/logging_config.py tests/test_logging_config.py
git commit -m "feat: add contextual rotating logging"
```

### Task 2: Add application session logging and exception coverage

**Files:**
- Modify: `main.py`
- Modify: `tests/test_logging_config.py`

- [ ] **Step 1: Add a failing launcher logging test**

Append:

```python
def test_launcher_uses_logging_setup_and_exception_logger():
    source = open("main.py", encoding="utf-8").read()
    assert "configure_logging" in source
    assert "new_session_id" in source
    assert "logger.exception" in source
    assert "with open(crash_log" not in source
```

- [ ] **Step 2: Run the test to verify RED**

```powershell
C:\ProgramData\anaconda3\envs\py39\python.exe -m pytest tests/test_logging_config.py::test_launcher_uses_logging_setup_and_exception_logger -q
```

Expected: failure because `main.py` still writes `crash.log` directly and does not configure the logging session.

- [ ] **Step 3: Integrate logging into `main.py`**

Add imports and module logger:

```python
from nanosense.utils.logging_config import (
    configure_logging,
    get_logger,
    logging_context,
    new_session_id,
)

logger = get_logger(__name__)
```

Replace `_install_global_excepthook()` with a hook that logs the current exception and then invokes the standard hook for `KeyboardInterrupt`:

```python
def _install_global_excepthook():
    def _hook(exc_type, exc_value, exc_tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return
        logger.error("uncaught_exception event=uncaught_exception", exc_info=(exc_type, exc_value, exc_tb))
        traceback.print_exception(exc_type, exc_value, exc_tb)

    sys.excepthook = _hook
```

At the start of `main()` configure logging and run the existing startup body under the session context:

```python
configure_logging()
_install_global_excepthook()
session_id = new_session_id()
with logging_context(session_id=session_id):
    return _run_application(argv)
```

Move the existing Qt setup and `app.exec_()` body into `_run_application(argv)` without changing its behavior. Replace launcher `print` calls with `logger.info`/`logger.warning` and event keys (`launcher_selection`, `main_window_started`, `main_window_start_failed`, `missing_app_icon`).

- [ ] **Step 4: Run launcher and logging tests**

```powershell
C:\ProgramData\anaconda3\envs\py39\python.exe -m pytest tests/test_logging_config.py tests/test_application_entrypoint.py -q
```

Expected: all selected tests pass.

- [ ] **Step 5: Commit application logging**

```powershell
git add main.py tests/test_logging_config.py nanosense/utils/logging_config.py
git commit -m "feat: initialize application logging session"
```

### Task 3: Add correlation events to acquisition and LSPR services

**Files:**
- Modify: `nanosense/core/acquisition.py`
- Modify: `nanosense/ml/lspr_ai_service.py`
- Modify: `tests/test_logging_config.py`

- [ ] **Step 1: Add failing event tests**

Append a stable event assertion using `caplog` and a local controller:

```python
def test_acquisition_and_lspr_logs_have_correlation_context(caplog):
    import time
    from nanosense.core.acquisition import AcquisitionService

    class Controller:
        def get_spectrum(self):
            return [500.0, 600.0], [1.0, 2.0]

    service = AcquisitionService(Controller(), poll_interval_s=0.001)
    with caplog.at_level(logging.INFO):
        assert service.start() is True
        time.sleep(0.02)
        assert service.stop(timeout_s=1.0) is True
    records = [record for record in caplog.records if record.name.startswith("nanosense.core.acquisition")]
    assert records
    assert any(record.correlation_id != "-" for record in records)
    assert any("acquisition_started" in record.getMessage() for record in records)
```

- [ ] **Step 2: Run to verify RED**

```powershell
C:\ProgramData\anaconda3\envs\py39\python.exe -m pytest tests/test_logging_config.py::test_acquisition_and_lspr_logs_have_correlation_context -q
```

Expected: failure because acquisition has no module logger or correlation event.

- [ ] **Step 3: Instrument service boundaries**

In `acquisition.py`, add `logger = get_logger(__name__)` and import `current_context`, `logging_context`, `new_correlation_id`. Store a correlation ID in `start()`/`start_batch()`, and wrap each worker body in `logging_context(correlation_id=self._correlation_id)`. Emit events without arrays:

```python
logger.info("acquisition_started event=acquisition_started")
logger.info("acquisition_stop_requested event=acquisition_stop_requested")
logger.warning("acquisition_stop_timeout event=acquisition_stop_timeout")
logger.exception("acquisition_failed event=acquisition_failed")
logger.info("acquisition_finished event=acquisition_finished")
```

Use the same pattern for batch start/stop/finish and log only `run_status`, task counts and IDs. In `lspr_ai_service.py`, add `logger = get_logger(__name__)`, create or inherit a correlation ID around public prediction calls, and log backend/mode/duration/error category without spectrum values.

- [ ] **Step 4: Run focused acquisition/LSPR tests**

```powershell
C:\ProgramData\anaconda3\envs\py39\python.exe -m pytest tests/test_logging_config.py tests/test_acquisition_lifecycle.py tests/test_lspr_ai_service.py tests/test_lspr_master_bridge.py -q
```

Expected: all selected tests pass.

- [ ] **Step 5: Commit service correlation logging**

```powershell
git add nanosense/core/acquisition.py nanosense/ml/lspr_ai_service.py tests/test_logging_config.py
git commit -m "feat: add acquisition and lspr correlation events"
```

### Task 4: Migrate controller, batch, and database critical events

**Files:**
- Modify: `nanosense/core/controller.py`
- Modify: `nanosense/core/batch_acquisition.py`
- Modify: `nanosense/core/database_manager.py`
- Modify: `README.md`
- Modify: `tests/test_logging_config.py`

- [ ] **Step 1: Add failing critical-event source/behavior checks**

Append:

```python
def test_critical_modules_define_module_loggers():
    for path in (
        "nanosense/core/controller.py",
        "nanosense/core/batch_acquisition.py",
        "nanosense/core/database_manager.py",
    ):
        source = open(path, encoding="utf-8").read()
        assert "get_logger(__name__)" in source


def test_readme_documents_log_location():
    source = open("README.md", encoding="utf-8").read()
    assert "logs/nanosense.log" in source
```

- [ ] **Step 2: Run to verify RED**

```powershell
C:\ProgramData\anaconda3\envs\py39\python.exe -m pytest tests/test_logging_config.py::test_critical_modules_define_module_loggers tests/test_logging_config.py::test_readme_documents_log_location -q
```

Expected: failure because the critical modules and README do not consistently reference the logging infrastructure.

- [ ] **Step 3: Replace high-value prints and broad silent catches**

Add module loggers to the three critical modules. Convert connection success/failure, controller fallback, batch start/finish/error, database initialization/migration/save failures to `logger.info`, `logger.warning`, or `logger.exception` with event keys. Preserve user-visible `QMessageBox` behavior and return values. For recoverable fallback exceptions include `exc_info=True` or `logger.exception`; for unrecoverable database errors retain existing exception propagation.

Do not log arrays, full paths containing user profiles, passwords, config dictionaries, or raw backend payloads. Leave low-value algorithm/report prints for a later focused migration.

Add a README section:

```markdown
### Runtime Logs

The application writes diagnostic logs to `logs/nanosense.log` with rotating backups.
Each record includes a session identifier and, for background work, a correlation identifier.
Logs contain task metadata and error tracebacks but do not include complete spectra or secrets.
```

- [ ] **Step 4: Run focused module tests**

```powershell
C:\ProgramData\anaconda3\envs\py39\python.exe -m pytest tests/test_logging_config.py tests/test_ocean_acquisition_recovery.py tests/test_database_manager_batch.py tests/test_lspr_ai_service.py -q
```

Expected: all selected tests pass.

- [ ] **Step 5: Commit critical module migration**

```powershell
git add nanosense/core/controller.py nanosense/core/batch_acquisition.py nanosense/core/database_manager.py README.md tests/test_logging_config.py
git commit -m "refactor: migrate critical paths to structured logging"
```

### Task 5: Full verification and delivery

**Files:**
- Modify: `tests/test_logging_config.py` only if deterministic Qt/logging synchronization needs tightening.

- [ ] **Step 1: Run complete verification**

```powershell
C:\ProgramData\anaconda3\envs\py39\python.exe -m pytest -q
C:\ProgramData\anaconda3\envs\py39\python.exe -m pip check
C:\ProgramData\anaconda3\envs\py39\python.exe -m compileall -q nanosense tests
git diff --check
git status --short
```

Expected: all tests pass, dependencies are consistent, bytecode compilation is silent, diff check is clean, and logs remain ignored/untracked.

- [ ] **Step 2: Commit only deterministic test synchronization if needed**

```powershell
git add tests/test_logging_config.py
git commit -m "test: stabilize logging context assertions"
```

- [ ] **Step 3: Merge and push**

After verification, merge the feature branch into `main`, rerun the complete test suite on merged `main`, and push `main` to `origin`.
