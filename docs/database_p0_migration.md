# Database P0 Iteration

This iteration intentionally starts without historical SQLite files. The source
project databases are not copied into this directory.

## Migration order

The embedded migration runner applies these migrations in order:

1. `0001_prepare_phase1_schema`
2. `0002_snapshot_soft_delete`
3. `0003_database_p0`

The second migration is registered explicitly before the P0 migration. The
third migration is idempotent and adds method metadata, analysis lineage
columns, and `quality_check_results`.

## Processing methods

Processing methods are canonical JSON payloads with a SHA-256 fingerprint. A
method version is immutable after it is applied. Saving changed parameters
creates a new method version; it does not update an existing snapshot.

## Quality control

Quality findings use `pass`, `warning`, or `fail` severity. Detailed findings
are stored in `quality_check_results`; `spectrum_sets.quality_flag` stores the
worst severity for fast filtering. Current checks cover finite values,
monotonic wavelengths, saturation, signal level, and required reference or
background spectra for ratio modes.

## Reanalysis

`DatabaseManager.create_analysis_run()` creates an append-only analysis run
with a processing configuration ID, source spectrum IDs, source-data hash,
parent run ID, and run kind. A reanalysis is therefore a new row linked to the
old run and cannot overwrite the original result.

## Verification

Use the py39 environment from the project root:

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
C:\ProgramData\anaconda3\envs\py39\python.exe -m pytest -q
```
