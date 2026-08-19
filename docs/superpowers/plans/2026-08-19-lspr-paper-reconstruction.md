# LSPR Paper-Aligned Workbench Reconstruction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the generic single-spectrum LSPR AI workflow with a paper-aligned paired-reference CEA workbench and a safe registry/interface for nine future analytes.

**Architecture:** Add domain modules for analyte definitions, paired spectra, validation, and model adapters. Keep the existing persistence and legacy result readers compatible by storing the new provenance in structured analysis context. Rebuild the prediction widget around paired input and route all predictions through analyte-specific adapters.

**Tech Stack:** Python 3.9, dataclasses, NumPy, PyQt5, SQLite JSON context, pytest.

---

### Task 1: Add analyte registry and domain contracts

**Files:**
- Create: `nanosense/ml/analyte_registry.py`
- Create: `nanosense/ml/paired_spectrum.py`
- Create: `nanosense/ml/analyte_model_protocol.py`
- Test: `tests/test_analyte_registry.py`
- Test: `tests/test_paired_spectrum.py`

- [ ] **Step 1: Write registry tests**

Add tests asserting the ten canonical IDs, ProGRP display normalization, alias lookup, supported/planned status, and unknown-analyte errors.

- [ ] **Step 2: Write pair validation tests**

Cover valid pairs, missing reference/response, mismatched lengths, non-finite values, unordered wavelengths, missing `chip_id`/`site_id`, and incompatible wavelength grids.

- [ ] **Step 3: Implement immutable domain dataclasses**

Implement `AnalyteDefinition`, `AnalyteRegistry`, `Spectrum`, and `PairedSpectrumInput`. Normalize values to plain Python lists and return typed `PairedSpectrumValidationError` details.

- [ ] **Step 4: Run focused tests**

Run `python -m pytest tests/test_analyte_registry.py tests/test_paired_spectrum.py -q` and require all tests to pass.

- [ ] **Step 5: Commit**

Commit `feat: add analyte and paired spectrum contracts`.

### Task 2: Add analyte model adapters and service routing

**Files:**
- Create: `nanosense/ml/analyte_model_adapters.py`
- Modify: `nanosense/ml/lspr_ai_service.py`
- Test: `tests/test_analyte_model_adapters.py`
- Test: `tests/test_lspr_ai_service.py`

- [ ] **Step 1: Write adapter tests**

Assert that planned analytes return `model_not_implemented`, CEA reports missing artifact/configuration without falling back to the generic engine, and a test adapter can return a typed result for service tests.

- [ ] **Step 2: Implement adapter protocol and unavailable adapter**

Provide `AnalytePredictionResult`, `AnalyteModelMetadata`, `UnavailableModelAdapter`, and a CEA adapter shell that validates the paired feature contract and checks a configured artifact manifest.

- [ ] **Step 3: Add service methods**

Add `LSPRAIService.predict_paired(input_data, options=None)` and `validate_paired_input(input_data)`. Route by `analyte_id`, preserve the existing generic methods for legacy callers, and ensure the new path never invokes `predict_single_spectrum`.

- [ ] **Step 4: Run focused tests**

Run `python -m pytest tests/test_analyte_model_adapters.py tests/test_lspr_ai_service.py -q`.

- [ ] **Step 5: Commit**

Commit `feat: route LSPR predictions through analyte adapters`.

### Task 3: Rebuild paired-prediction GUI

**Files:**
- Create: `nanosense/gui/lspr_paired_prediction_widget.py`
- Modify: `nanosense/gui/lspr_ai_analysis_window.py`
- Modify: `nanosense/gui/lspr_single_prediction_widget.py`
- Test: `tests/test_lspr_paired_prediction_widget.py`

- [ ] **Step 1: Write behavior tests**

Create an offscreen QApplication test that selects CEA and a planned analyte, loads a valid pair, asserts validation status, verifies planned prediction is disabled, and verifies no numeric result appears after an unavailable-model attempt.

- [ ] **Step 2: Implement paired input controls**

Add analyte combo box, reference/response import actions, chip/site fields, validation summary, and a prediction action that calls `predict_paired` only after validation succeeds.

- [ ] **Step 3: Integrate the new widget**

Make the analysis window use the paired widget as the primary tab. Keep comparison/digital-twin tabs available only as secondary visualization tabs and keep legacy single-spectrum records readable.

- [ ] **Step 4: Run GUI tests**

Run `python -m pytest tests/test_lspr_paired_prediction_widget.py -q` with `QT_QPA_PLATFORM=offscreen`.

- [ ] **Step 5: Commit**

Commit `feat: rebuild LSPR workbench around paired spectra`.

### Task 4: Persist provenance and update documentation

**Files:**
- Modify: `nanosense/gui/lspr_ai_analysis_window.py`
- Modify: `nanosense/core/database_manager.py`
- Modify: `docs/lspr_ai_workbench/lspr-ai-workbench-user-guide.md`
- Modify: `README.md`
- Test: `tests/test_lspr_ai_database.py`

- [ ] **Step 1: Write persistence tests**

Assert that archived paired results contain analyte ID, chip/site IDs, reference/response links, pairing status, preprocessing version, model key, and legacy classification.

- [ ] **Step 2: Store structured paired context**

Extend the existing analysis context writer without changing old table shape. Preserve JSON compatibility and ensure legacy generic records remain readable.

- [ ] **Step 3: Update user-facing documentation**

Document the ten analytes, the CEA paired-reference workflow, planned-model behavior, artifact requirements, and the research-use-only limitation. Remove claims that the generic single-spectrum engine implements the manuscript model.

- [ ] **Step 4: Run persistence tests**

Run `python -m pytest tests/test_lspr_ai_database.py -q`.

- [ ] **Step 5: Commit**

Commit `docs: document paper-aligned LSPR workflow`.

### Task 5: Full verification and integration

**Files:**
- Test: all existing tests and new LSPR tests

- [ ] **Step 1: Run the complete test suite**

Run `C:\ProgramData\anaconda3\envs\py39\python.exe -m pytest -q`.

- [ ] **Step 2: Run static checks**

Run `python -m pip check`, `python -m compileall -q .`, and `git diff --check`.

- [ ] **Step 3: Review the diff**

Confirm no model artifacts, database files, logs, secrets, or host-specific paths were added.

- [ ] **Step 4: Commit and merge**

Merge the feature branch into `main`, rerun the complete test suite on the merged result, push `origin/main`, and remove the merged worktree and branch.
