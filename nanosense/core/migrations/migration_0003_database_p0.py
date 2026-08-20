"""Database P0 schema for methods, quality checks, and reanalysis lineage."""

import sqlite3


MIGRATION_ID = "0003_database_p0"


def _column_exists(conn, table_name, column_name):
    return any(
        row[1] == column_name
        for row in conn.execute(f"PRAGMA table_info({table_name})")
    )


def _add_column(conn, table_name, column_name, definition):
    if not _column_exists(conn, table_name, column_name):
        conn.execute(
            f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}"
        )


def _create_index(conn, name, statement):
    conn.execute(f"CREATE INDEX IF NOT EXISTS {name} ON {statement}")


def apply(conn: sqlite3.Connection) -> None:
    snapshot_columns = [
        ("method_type", "TEXT NOT NULL DEFAULT 'measurement'"),
        ("mode", "TEXT"),
        ("description", "TEXT"),
        ("is_template", "INTEGER NOT NULL DEFAULT 0"),
        ("fingerprint", "TEXT"),
        ("parent_config_id", "INTEGER REFERENCES processing_snapshots(processing_config_id)"),
    ]
    for column_name, definition in snapshot_columns:
        _add_column(conn, "processing_snapshots", column_name, definition)

    analysis_columns = [
        ("processing_config_id", "INTEGER REFERENCES processing_snapshots(processing_config_id)"),
        ("parent_analysis_run_id", "INTEGER REFERENCES analysis_runs(analysis_run_id)"),
        ("source_fingerprint", "TEXT"),
        ("run_kind", "TEXT NOT NULL DEFAULT 'analysis'"),
    ]
    for column_name, definition in analysis_columns:
        _add_column(conn, "analysis_runs", column_name, definition)

    _add_column(
        conn,
        "spectrum_sets",
        "source_spectrum_set_id",
        "INTEGER REFERENCES spectrum_sets(spectrum_set_id)",
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS quality_check_results (
            quality_check_id INTEGER PRIMARY KEY AUTOINCREMENT,
            spectrum_set_id INTEGER REFERENCES spectrum_sets(spectrum_set_id) ON DELETE CASCADE,
            analysis_run_id INTEGER REFERENCES analysis_runs(analysis_run_id) ON DELETE CASCADE,
            rule_key TEXT NOT NULL,
            severity TEXT NOT NULL,
            status TEXT NOT NULL,
            measured_value REAL,
            threshold_value REAL,
            unit TEXT,
            message TEXT NOT NULL,
            details_json TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )

    _create_index(
        conn,
        "idx_processing_snapshots_fingerprint",
        "processing_snapshots(fingerprint)",
    )
    _create_index(
        conn,
        "idx_processing_snapshots_template",
        "processing_snapshots(is_template, is_active, name)",
    )
    _create_index(
        conn,
        "idx_analysis_runs_processing_config",
        "analysis_runs(processing_config_id)",
    )
    _create_index(
        conn,
        "idx_analysis_runs_parent",
        "analysis_runs(parent_analysis_run_id)",
    )
    _create_index(
        conn,
        "idx_spectrum_sets_source",
        "spectrum_sets(source_spectrum_set_id)",
    )
    _create_index(
        conn,
        "idx_quality_checks_spectrum",
        "quality_check_results(spectrum_set_id, created_at)",
    )
    _create_index(
        conn,
        "idx_quality_checks_run",
        "quality_check_results(analysis_run_id, created_at)",
    )
