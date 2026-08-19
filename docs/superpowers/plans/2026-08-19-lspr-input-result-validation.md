# LSPR Input And Result Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add shared LSPR input validation, stable error classification, result provenance, and traceable database archiving without changing valid prediction behavior.

**Architecture:** `lspr_backend_protocol.py` owns pure validation rules and error-code constants. `LSPRAIService` validates every public request, maps backend errors to a typed service exception, and attaches UTC provenance to successful results. Backends classify execution failures and log exception chains; the existing database archive stores provenance in `input_context` and derives an algorithm version when one is not explicitly supplied.

**Tech Stack:** Python 3.9, dataclasses, `math`, `datetime`, standard `logging`, PyQt5, sqlite3, pytest.

---

## File Map

- Create `tests/test_lspr_backend_protocol.py`: pure request validation and error-code tests.
- Modify `nanosense/ml/lspr_backend_protocol.py`: validation helpers, validation exception, and stable error-code constants.
- Modify `nanosense/ml/lspr_ai_service.py`: service validation, typed errors, logging, and provenance fields.
- Modify `tests/test_lspr_ai_service.py`: service rejection, backend error mapping, provenance, and no-backend-call tests.
- Modify `nanosense/ml/lspr_inprocess_backend.py`: classify model failures and log exception chains.
- Modify `nanosense/ml/lspr_subprocess_backend.py`: classify runner failures, invalid JSON, missing runner, and timeouts.
- Modify `tests/test_lspr_master_bridge.py`: backend error-code and timeout tests.
- Modify `nanosense/core/database_manager.py`: persist provenance context and derive `algorithm_version` when omitted.
- Modify `tests/test_lspr_ai_database.py`: assert provenance and algorithm-version persistence.
- Modify `nanosense/gui/lspr_single_prediction_widget.py` and `nanosense/gui/lspr_batch_prediction_widget.py`: show safe typed error messages and avoid uncaught batch failures.
- Create `tests/test_lspr_widget_validation.py`: focused offscreen widget tests for safe prediction and batch error handling.
- Modify `docs/lspr_ai_workbench/lspr-ai-workbench-user-guide.md`: document validation rules and error categories.

### Task 1: Define and test protocol-level validation

**Files:**
- Create: `tests/test_lspr_backend_protocol.py`
- Modify: `nanosense/ml/lspr_backend_protocol.py`

- [ ] **Step 1: Write failing validation tests.**

Add tests for the public helper API below:

```python
from nanosense.ml.lspr_backend_protocol import (
    LSPRValidationError,
    validate_concentration,
    validate_spectrum,
)

def test_validate_spectrum_accepts_three_point_increasing_finite_arrays():
    assert validate_spectrum([500.0, 501.0, 502.0], [0.1, 0.2, 0.3]) is None

@pytest.mark.parametrize("wavelengths, intensities", [
    ([], []),
    ([500.0, 501.0], [0.1]),
    ([500.0, 501.0], [0.1, 0.2]),
    ([500.0, float("nan"), 502.0], [0.1, 0.2, 0.3]),
    ([500.0, 499.0, 502.0], [0.1, 0.2, 0.3]),
])
def test_validate_spectrum_rejects_invalid_arrays(wavelengths, intensities):
    with pytest.raises(LSPRValidationError) as exc_info:
        validate_spectrum(wavelengths, intensities)
    assert exc_info.value.code == "input_invalid"

def test_validate_concentration_rejects_negative_and_non_finite_values():
    for value in (-1.0, float("nan"), float("inf")):
        with pytest.raises(LSPRValidationError) as exc_info:
            validate_concentration(value)
        assert exc_info.value.code == "input_invalid"
```

- [ ] **Step 2: Run the new tests and verify RED.**

```powershell
& 'C:\ProgramData\anaconda3\envs\py39\python.exe' -m pytest tests/test_lspr_backend_protocol.py -q
```

Expected: FAIL because the validation helpers and exception do not exist.

- [ ] **Step 3: Implement minimal pure validation.**

Add constants for `input_invalid`, `configuration_error`, `model_error`, `external_process_error`, `request_timeout`, and `cancelled`. Implement `LSPRValidationError(ValueError)` with `code`, `message`, and JSON-compatible `details`. `validate_spectrum()` must check equal lengths, minimum length 3, finite numeric values, and strict wavelength increase. `validate_concentration()` must accept finite values greater than or equal to zero.

- [ ] **Step 4: Run protocol tests and the existing protocol serialization tests.**

```powershell
& 'C:\ProgramData\anaconda3\envs\py39\python.exe' -m pytest tests/test_lspr_backend_protocol.py tests/test_lspr_master_bridge.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit the protocol contract.**

```powershell
git add nanosense/ml/lspr_backend_protocol.py tests/test_lspr_backend_protocol.py
git commit -m "feat: validate LSPR request inputs"
```

### Task 2: Validate service entry points and attach provenance

**Files:**
- Modify: `nanosense/ml/lspr_ai_service.py`
- Modify: `tests/test_lspr_ai_service.py`

- [ ] **Step 1: Add failing service tests.**

Extend the stub backend with call counters and add tests that invalid single, comparison, digital-twin, and empty-batch inputs raise `LSPRAIServiceError` with `code == "input_invalid"` without calling the backend. Add a successful prediction assertion:

```python
result = service.predict_single_spectrum(
    [500.0, 501.0, 502.0], [0.1, 0.2, 0.3], metadata={"source": "unit-test"}
)
assert result.provenance["backend"] == "stub"
assert result.provenance["model_mode"] == "auto"
assert result.provenance["metadata"] == {"source": "unit-test"}
assert result.provenance["requested_at"].endswith("+00:00")
```

Add a backend-error test asserting `_raise_if_error()` raises `LSPRAIServiceError` with the response code and details preserved.

- [ ] **Step 2: Run service tests and verify RED.**

```powershell
& 'C:\ProgramData\anaconda3\envs\py39\python.exe' -m pytest tests/test_lspr_ai_service.py -q
```

Expected: FAIL because service validation, typed errors, and provenance fields do not exist.

- [ ] **Step 3: Implement service validation and provenance.**

Add `LSPRAIServiceError(RuntimeError)` with `code` and `details`. Validate all public methods before constructing backend requests; for digital twin validate the optional wavelength/intensity pair and concentration; for batch reject empty input and include the failing item index in `details`. Add `provenance` fields with default dictionaries to `LSPRPredictionResult`, `LSPRSpectrumComparisonResult`, and `LSPRDigitalTwinResult`. Build provenance with `datetime.now(timezone.utc).isoformat()`, the selected model mode, response backend, and a copied metadata dictionary. Return request-level provenance alongside batch rows.

- [ ] **Step 4: Run service tests and verify GREEN.**

```powershell
& 'C:\ProgramData\anaconda3\envs\py39\python.exe' -m pytest tests/test_lspr_ai_service.py tests/test_lspr_backend_protocol.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit service validation and provenance.**

```powershell
git add nanosense/ml/lspr_ai_service.py tests/test_lspr_ai_service.py
git commit -m "feat: add LSPR service validation and provenance"
```

### Task 3: Classify backend failures and preserve exception chains

**Files:**
- Modify: `nanosense/ml/lspr_inprocess_backend.py`
- Modify: `nanosense/ml/lspr_subprocess_backend.py`
- Modify: `tests/test_lspr_master_bridge.py`

- [ ] **Step 1: Add failing backend error-code tests.**

Make the stub in-process engine raise `RuntimeError` and assert the response code is `model_error`. Monkeypatch `subprocess.run` to raise `subprocess.TimeoutExpired` and assert `SubprocessLSPRBackend.health_check()` or a prediction response uses `request_timeout`. Assert missing runner, non-zero exit, and invalid JSON use `external_process_error` and include runner/return-code details.

- [ ] **Step 2: Run focused tests and verify RED.**

```powershell
& 'C:\ProgramData\anaconda3\envs\py39\python.exe' -m pytest tests/test_lspr_master_bridge.py -k "error_code or timeout or runner" -q
```

Expected: FAIL because existing responses use operation-specific codes and do not catch timeouts.

- [ ] **Step 3: Implement minimal backend mapping and logging.**

Use module loggers and `logger.exception()` in in-process model catches. Map model exceptions to `ErrorResponse(code="model_error", details={"exception_type": ...})`. In the subprocess invocation, catch `subprocess.TimeoutExpired` and return `request_timeout`; map missing runner, non-zero return, and JSON decode failures to `external_process_error`, retaining runner path, stderr, return code, and exception type in details. Keep response payload fields unchanged.

- [ ] **Step 4: Run backend and service regression tests.**

```powershell
& 'C:\ProgramData\anaconda3\envs\py39\python.exe' -m pytest tests/test_lspr_master_bridge.py tests/test_lspr_ai_service.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit backend error classification.**

```powershell
git add nanosense/ml/lspr_inprocess_backend.py nanosense/ml/lspr_subprocess_backend.py tests/test_lspr_master_bridge.py
git commit -m "feat: classify LSPR backend failures"
```

### Task 4: Persist provenance in LSPR archives and protect GUI error paths

**Files:**
- Modify: `nanosense/core/database_manager.py`
- Modify: `tests/test_lspr_ai_database.py`
- Modify: `nanosense/gui/lspr_single_prediction_widget.py`
- Modify: `nanosense/gui/lspr_batch_prediction_widget.py`
- Create: `tests/test_lspr_widget_validation.py`

- [ ] **Step 1: Add failing archive and GUI assertions.**

 Pass `input_context={"model_mode": "v2", "provenance": {"backend": "stub", "requested_at": "2026-08-19T00:00:00+00:00", "metadata": {"source": "unit-test"}}}` without an explicit `algorithm_version`; assert the stored `analysis_runs.algorithm_version` is `v2` and the JSON context preserves provenance. Add `tests/test_lspr_widget_validation.py` with an offscreen `QApplication`, a stub service that raises `LSPRAIServiceError` carrying traceback-like details, and assertions that the single widget's message box receives only the safe message. Add a batch widget test that catches the same service error and leaves the table unchanged while showing a warning.

- [ ] **Step 2: Run archive/GUI tests and verify RED.**

```powershell
& 'C:\ProgramData\anaconda3\envs\py39\python.exe' -m pytest tests/test_lspr_ai_database.py tests/test_lspr_widget_validation.py -q
```

Expected: FAIL because archive version derivation and guarded batch error handling do not exist.

- [ ] **Step 3: Implement archive provenance and safe GUI handling.**

In `save_lspr_ai_prediction()`, copy `input_context`, derive `algorithm_version` from `model_version` or `model_mode` only when the parameter is `None`, and serialize provenance through the existing JSON context. In the single and batch widgets, catch `LSPRAIServiceError`/`RuntimeError`, show only `str(exc)`, and avoid writing partial result rows on failure.

- [ ] **Step 4: Run archive and GUI tests.**

```powershell
& 'C:\ProgramData\anaconda3\envs\py39\python.exe' -m pytest tests/test_lspr_ai_database.py tests/test_lspr_ai_workbench_plan_smoke.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit archive and GUI protections.**

```powershell
git add nanosense/core/database_manager.py tests/test_lspr_ai_database.py nanosense/gui/lspr_single_prediction_widget.py nanosense/gui/lspr_batch_prediction_widget.py tests/test_lspr_widget_validation.py
git commit -m "feat: preserve LSPR provenance in archives"
```

### Task 5: Document and complete verification

**Files:**
- Modify: `docs/lspr_ai_workbench/lspr-ai-workbench-user-guide.md`

- [ ] **Step 1: Document validation and error behavior.**

Add a section describing the accepted spectrum shape, the no-hardcoded-range policy, the stable error codes, and provenance fields recorded for archived predictions.

- [ ] **Step 2: Run focused and complete verification.**

```powershell
& 'C:\ProgramData\anaconda3\envs\py39\python.exe' -m pytest tests/test_lspr_backend_protocol.py tests/test_lspr_ai_service.py tests/test_lspr_master_bridge.py tests/test_lspr_ai_database.py tests/test_lspr_widget_validation.py -q
& 'C:\ProgramData\anaconda3\envs\py39\python.exe' -m pytest -q
& 'C:\ProgramData\anaconda3\envs\py39\python.exe' -m pip check
& 'C:\ProgramData\anaconda3\envs\py39\python.exe' -m compileall -q nanosense tests
```

Expected: focused and complete suites pass, `pip check` reports no broken requirements, and `compileall` exits successfully. The two known `file_io.py` deprecation warnings may remain.

- [ ] **Step 3: Commit documentation and final verification.**

```powershell
git add docs/lspr_ai_workbench/lspr-ai-workbench-user-guide.md
git commit -m "docs: document LSPR validation and provenance"
```
