# Database P0 Design

## Goal

Add three P0 capabilities to the iteration copy without deleting application tables: versioned processing methods, persisted quality-control results, and append-only reanalysis lineage.

## Data rules

- The iteration copy starts with an empty application database; the source project's historical databases remain untouched.
- Raw spectrum data is immutable after capture. Reprocessed data is stored as a new structured spectrum record.
- A processing method is immutable once applied. Editing a method creates a new version.
- Reanalysis never overwrites an existing analysis run; it creates a new run linked to the source run and processing snapshot.
- Existing legacy tables remain readable during the iteration. New structured writes remain the preferred path.

## Schema approach

Use the existing SQLite migration runner. Register the existing soft-delete migration first, then add one P0 migration that:

- extends `processing_snapshots` with method metadata and a content fingerprint;
- adds processing and lineage references to `analysis_runs` and `spectrum_sets`;
- adds `quality_check_results` for detailed QC findings while retaining `spectrum_sets.quality_flag` as the summary state;
- creates indexes for method lookup, lineage lookup, and QC lookup.

The migration must be idempotent and must work for a fresh database and a database created by the previous schema.

## Application boundaries

- `nanosense/core/processing_methods.py` builds and validates canonical method payloads.
- `nanosense/core/quality_control.py` runs deterministic, GUI-independent checks.
- `DatabaseManager` owns persistence, method listing, QC persistence, and analysis lineage.
- `MeasurementWidget` exposes save/apply method actions and displays the latest QC summary.
- Database Explorer exposes reanalysis input selection and shows QC/version metadata.

## Verification

Tests cover migration idempotency, method fingerprint stability, QC severity rules, immutable method versions, append-only reanalysis, and preservation of raw spectrum hashes. Full py39 tests and compile checks run before the database-P0 commit.
