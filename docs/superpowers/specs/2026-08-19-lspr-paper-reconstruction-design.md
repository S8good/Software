# LSPR Paper-Aligned Workbench Reconstruction

## Decision

Reconstruct the LSPR workbench around the paired-reference CEA quantification method described in the manuscript. The supported scientific workflow will require a BSA reference spectrum and a CEA reaction spectrum from the same sensor chip and sensing site. The existing generic single-spectrum AI flow will remain readable for legacy records but will no longer be presented as the paper method.

The first implementation registers ten analytes:

| ID | Display name | Status |
| --- | --- | --- |
| `cea` | CEA | supported contract; model artifact remains separately deployable |
| `nse` | NSE | planned |
| `cyfra21_1` | Cyfra21-1 | planned |
| `progrp` | ProGRP | planned |
| `scca` | SCCA | planned |
| `p53` | p53 | planned |
| `ca125` | CA125 | planned |
| `tsgf` | TSGF | planned |
| `gage7` | GAGE-7 | planned |
| `mage_a1` | MAGE-A1 | planned |

Planned analytes can be selected, imported, validated, and archived. They cannot produce a concentration and must return a structured `model_not_implemented` error.

## Domain boundaries

### Analyte registry

`AnalyteDefinition` is the stable metadata contract. IDs are ASCII-safe and immutable; display names and aliases are presentation metadata. Each definition declares status, target unit, reference state, model key, and input-contract version. `AnalyteRegistry` resolves IDs and aliases and rejects unknown analytes with a typed configuration error.

### Paired spectrum input

`PairedSpectrumInput` contains `analyte_id`, `chip_id`, `site_id`, a reference `Spectrum`, a response `Spectrum`, optional nominal concentration, and acquisition metadata. The value is immutable after validation. Validation checks finite numeric values, equal lengths, strictly increasing wavelengths, minimum point count, matching pair identity, and model-declared wavelength constraints. Resampling and preprocessing are explicit operations that return a versioned audit record rather than silently mutating raw input.

### Model adapters

`AnalyteModelAdapter` exposes `health_check`, `validate_input`, `predict_pair`, `predict_batch`, and `model_metadata`. `UnavailableModelAdapter` is used for planned analytes and never returns a fabricated result. `CEA` uses a paper-aligned adapter contract with response spectrum, first derivative, and three paired BSA descriptors as model features; the target is log10 concentration and the result is reported in ng/mL with provenance and QC.

The repository does not contain the paper dataset or trained artifacts. Therefore the adapter must report unavailable model artifacts explicitly until a compatible, versioned artifact is supplied. A mock adapter may be used only in tests and must be clearly marked as test-only.

### Persistence and compatibility

Existing `spectrum_sets`, `analysis_runs`, and `input_context` storage remain the compatibility layer. New LSPR records store `analyte_id`, `chip_id`, `site_id`, reference/response spectrum IDs, pairing status, preprocessing version, model key, and model version in structured context. Existing generic records are tagged `legacy_generic` and are not reinterpreted as CEA results.

## User workflow

1. Select an analyte from the ten-item registry.
2. Import or choose the reference and response spectra.
3. Enter or load chip/site identifiers.
4. Review pair validation and QC results.
5. Run prediction only when the selected analyte has a healthy model adapter.
6. Archive the paired input, QC, model metadata, and result provenance.

The workbench will expose a dedicated paired-prediction page. Comparison plots and synthetic digital-twin tools are secondary visualization extensions and cannot be used to create a scientific prediction without a valid paired input and supported adapter.

## Error and safety behavior

- Unknown analyte, malformed pair, missing identifiers, and incompatible grids produce actionable input/configuration errors.
- Planned analytes show a disabled prediction action and an explicit model-unavailable explanation.
- Missing CEA artifacts show the required artifact paths and model contract version; no fallback to the generic single-spectrum model occurs in the paper workflow.
- Results are labeled research-use analytical estimates, not clinical diagnoses.

## Verification criteria

- Registry tests cover all ten IDs, aliases, status, and ProGRP normalization.
- Pair validation tests cover missing spectra, mismatched lengths/grids, non-finite values, unordered wavelengths, missing chip/site IDs, and analyte/model mismatch.
- Adapter tests prove planned analytes never return numeric predictions and CEA reports missing artifacts deterministically.
- GUI behavior tests select analytes, load a valid pair, show validation state, disable planned prediction, and never display a fabricated concentration.
- Full regression suite, `pip check`, `compileall`, and `git diff --check` pass before merge.
