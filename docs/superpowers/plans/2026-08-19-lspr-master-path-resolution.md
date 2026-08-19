# LSPR Master Path Resolution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the host-specific LSPR Master path fallback and provide portable path resolution, structured health diagnostics, and configurable subprocess Python settings.

**Architecture:** Keep path resolution in `LSPRMasterBridge`, which becomes the single source of truth for explicit, environment, and adjacent-directory lookup. Backends expose bridge/runner diagnostics through the existing health-check response, while `SettingsDialog` provides non-persisting connection validation for the current form values.

**Tech Stack:** Python 3.9, `pathlib`, PyQt5, pytest, existing LSPR backend protocol and configuration manager.

---

## File Map

- Modify `nanosense/ml/lspr_master_bridge.py`: root resolution, validation diagnostics, and a structured path error.
- Modify `nanosense/ml/lspr_inprocess_backend.py`: expose bridge diagnostics when health checks fail.
- Modify `nanosense/ml/lspr_subprocess_backend.py`: use the configured interpreter and expose runner/interpreter diagnostics consistently.
- Modify `nanosense/utils/config_manager.py`: add the `lspr_subprocess_python` default.
- Modify `nanosense/gui/settings_dialog.py`: add Python interpreter selection and a non-persisting connection test.
- Modify `tests/test_lspr_master_bridge.py`: path resolution and diagnostics tests.
- Modify `tests/test_lspr_settings_integration.py`: configuration and connection-test tests.
- Modify `tests/test_lspr_ai_workbench_plan_smoke.py`: assert the new default and controls.
- Modify `README.md` and `docs/lspr_ai_workbench/lspr-ai-workbench-user-guide.md`: document portable path setup and diagnostics.

### Task 1: Add failing bridge path-resolution tests

**Files:**
- Modify: `tests/test_lspr_master_bridge.py`

- [ ] **Step 1: Add a reusable temporary Master fixture.**

Add a helper that creates every file in `LSPRMasterBridge.REQUIRED_FILES` below a supplied `tmp_path`, so resolver tests exercise the real validation contract:

```python
def make_master_root(tmp_path):
    root = tmp_path / "LSPR_Spectra_Master"
    for relative_path, _ in LSPRMasterBridge.REQUIRED_FILES:
        target = root / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("# test fixture", encoding="utf-8")
    return root
```

- [ ] **Step 2: Add tests for explicit, environment, and adjacent precedence.**

Use `monkeypatch.setenv("LSPR_MASTER_ROOT", ...)` and patch the bridge's project-root helper (or candidate-root method) to a temporary directory. Assert `bridge.master_root` and `bridge.diagnostics()["resolution_source"]` are `explicit`, `environment`, and `adjacent` respectively.

- [ ] **Step 3: Add tests for structured missing-root and missing-file errors.**

Assert an invalid root raises `LSPRMasterPathError`, its message contains the attempted root and repair guidance, and its `diagnostics` mapping contains `candidate_paths`. Create a root with one required file omitted and assert `missing_files` contains that relative path.

- [ ] **Step 4: Run only the new tests to verify the expected RED state.**

Run:

```powershell
& 'C:\ProgramData\anaconda3\envs\py39\python.exe' -m pytest tests/test_lspr_master_bridge.py -k "resolution or missing_file or missing_root" -q
```

Expected: FAIL because `LSPRMasterPathError`, resolution-source diagnostics, and adjacent lookup do not exist yet.

- [ ] **Step 5: Commit the failing tests.**

```powershell
git add tests/test_lspr_master_bridge.py
git commit -m "test: specify portable LSPR master resolution"
```

### Task 2: Implement bridge resolution and diagnostics

**Files:**
- Modify: `nanosense/ml/lspr_master_bridge.py`
- Test: `tests/test_lspr_master_bridge.py`

- [ ] **Step 1: Add the structured error and diagnostic fields.**

Add `LSPRMasterPathError(FileNotFoundError)` with a public `diagnostics` dictionary. Extend `LSPRMasterDiagnostics` with `resolution_source`, `candidate_paths`, `missing_files`, `runner_path`, and `python_executable`, using immutable/empty-safe defaults.

- [ ] **Step 2: Implement deterministic candidate construction.**

Add a class/static helper that returns normalized candidates in this order:

```python
software_root = Path(__file__).resolve().parents[2]
(
    software_root / "LSPR_Spectra_Master",
    software_root.parent / "DeepLearning" / "LSPR_Spectra_Master",
    software_root.parent.parent / "DeepLearning" / "LSPR_Spectra_Master",
)
```

Skip empty explicit values, normalize every candidate with `expanduser().resolve()`, and select the first existing directory. Never include the old developer absolute path or a machine-specific fallback.

- [ ] **Step 3: Validate required files while preserving diagnostics.**

Store the selected root, source, candidates, missing relative paths, runner path, and `sys.executable` before validation. Raise `LSPRMasterPathError` with those details when no directory exists or required files are missing. Keep `validate_required_files()` callable and make `diagnostics()` return a JSON-serializable dictionary.

- [ ] **Step 4: Run the bridge tests to verify GREEN.**

Run:

```powershell
& 'C:\ProgramData\anaconda3\envs\py39\python.exe' -m pytest tests/test_lspr_master_bridge.py -q
```

Expected: all bridge tests pass, including the new resolution and diagnostics tests.

- [ ] **Step 5: Commit the bridge implementation.**

```powershell
git add nanosense/ml/lspr_master_bridge.py tests/test_lspr_master_bridge.py
git commit -m "feat: resolve LSPR master paths portably"
```

### Task 3: Propagate health diagnostics through both backends

**Files:**
- Modify: `nanosense/ml/lspr_inprocess_backend.py`
- Modify: `nanosense/ml/lspr_subprocess_backend.py`
- Modify: `tests/test_lspr_master_bridge.py`

- [ ] **Step 1: Add failing health-diagnostic assertions.**

For an in-process backend with an invalid root, assert `health_check().details` includes `candidate_paths` and `missing_files`. For a subprocess backend with a configured runner path and Python interpreter, monkeypatch `_invoke_runner` and assert the health response details preserve `runner_path` and `python_executable`.

- [ ] **Step 2: Run the focused tests and confirm RED.**

```powershell
& 'C:\ProgramData\anaconda3\envs\py39\python.exe' -m pytest tests/test_lspr_master_bridge.py -k "health.*diagnostic or runner.*diagnostic" -q
```

Expected: FAIL because current health responses omit the structured fields.

- [ ] **Step 3: Implement minimal diagnostic propagation.**

In `InProcessLSPRBackend.health_check()`, use `getattr(exc, "diagnostics", {})` and merge `{"lspr_backend_mode": "inprocess"}`. In `SubprocessLSPRBackend`, resolve the runner from explicit `lspr_runner_path` or configured master root, and include normalized runner path and Python executable in every health/error detail. Keep the existing response schema and error codes.

- [ ] **Step 4: Run backend tests.**

```powershell
& 'C:\ProgramData\anaconda3\envs\py39\python.exe' -m pytest tests/test_lspr_master_bridge.py tests/test_lspr_ai_service.py -q
```

Expected: PASS with no new failures.

- [ ] **Step 5: Commit backend diagnostics.**

```powershell
git add nanosense/ml/lspr_inprocess_backend.py nanosense/ml/lspr_subprocess_backend.py tests/test_lspr_master_bridge.py
git commit -m "feat: expose LSPR backend health diagnostics"
```

### Task 4: Add interpreter configuration and connection testing to settings

**Files:**
- Modify: `nanosense/utils/config_manager.py`
- Modify: `nanosense/gui/settings_dialog.py`
- Modify: `tests/test_lspr_settings_integration.py`
- Modify: `tests/test_lspr_ai_workbench_plan_smoke.py`

- [ ] **Step 1: Add failing configuration and widget tests.**

Assert `get_default_settings()["lspr_subprocess_python"] == ""`. Instantiate `SettingsDialog`, assert the interpreter edit and test button exist, set an interpreter value, call `_save_and_accept()`, and assert it is retained. Monkeypatch `create_lspr_backend` with a stub returning `HealthCheckResponse(ok=True, backend="stub", details={"master_root": "..."})`; assert `_test_lspr_connection()` calls it with the current form values and does not write the config file.

- [ ] **Step 2: Run the new settings tests to confirm RED.**

```powershell
& 'C:\ProgramData\anaconda3\envs\py39\python.exe' -m pytest tests/test_lspr_settings_integration.py tests/test_lspr_ai_workbench_plan_smoke.py -k "subprocess_python or connection" -q
```

Expected: FAIL because the setting and controls do not exist.

- [ ] **Step 3: Implement the default and controls.**

Add `lspr_subprocess_python` to `get_default_settings()`. In `SettingsDialog`, add a file-picker row using `QFileDialog.getOpenFileName`, a `Test Connection` button, and a method that builds a temporary config from the current fields, calls `create_lspr_backend(config).health_check()`, and displays only a summary via `QMessageBox`. Do not call `save_settings()` from the test method. Persist the interpreter value in `_save_and_accept()` and populate it in `_populate_initial_values()`.

- [ ] **Step 4: Run the settings tests to verify GREEN.**

```powershell
& 'C:\ProgramData\anaconda3\envs\py39\python.exe' -m pytest tests/test_lspr_settings_integration.py tests/test_lspr_ai_workbench_plan_smoke.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit the settings changes.**

```powershell
git add nanosense/utils/config_manager.py nanosense/gui/settings_dialog.py tests/test_lspr_settings_integration.py tests/test_lspr_ai_workbench_plan_smoke.py
git commit -m "feat: add configurable LSPR subprocess interpreter"
```

### Task 5: Document setup and run the complete verification suite

**Files:**
- Modify: `README.md`
- Modify: `docs/lspr_ai_workbench/lspr-ai-workbench-user-guide.md`

- [ ] **Step 1: Document the resolution order and settings.**

Add a concise setup section stating that `lspr_master_root` overrides `LSPR_MASTER_ROOT`, which overrides adjacent-directory detection; document `lspr_subprocess_python`, the test-connection action, and the structured diagnostics shown for missing model files.

- [ ] **Step 2: Run the focused and complete checks.**

```powershell
& 'C:\ProgramData\anaconda3\envs\py39\python.exe' -m pytest tests/test_lspr_master_bridge.py tests/test_lspr_settings_integration.py tests/test_lspr_ai_workbench_plan_smoke.py -q
& 'C:\ProgramData\anaconda3\envs\py39\python.exe' -m pytest -q
& 'C:\ProgramData\anaconda3\envs\py39\python.exe' -m pip check
& 'C:\ProgramData\anaconda3\envs\py39\python.exe' -m compileall -q nanosense tests
```

Expected: focused and complete suites pass, `pip check` reports no broken requirements, and `compileall` exits successfully. Existing deprecation warnings in `nanosense/utils/file_io.py` may remain and are outside this change.

- [ ] **Step 3: Search for the removed hard-coded path.**

```powershell
rg -n "3\.LSPR-code|LSPR_Spectra_Master" nanosense tests README.md docs/lspr_ai_workbench
```

Expected: no `3.LSPR-code` machine path; only portable names, configuration keys, and documentation remain.

- [ ] **Step 4: Commit documentation and final verification.**

```powershell
git add README.md docs/lspr_ai_workbench/lspr-ai-workbench-user-guide.md
git commit -m "docs: document portable LSPR setup"
```

