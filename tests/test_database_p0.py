import importlib
import sqlite3

import pytest

from nanosense.core.migration_runner import run_migrations


def _create_legacy_schema(conn):
    conn.executescript(
        """
        CREATE TABLE projects (
            project_id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            description TEXT,
            creation_date TEXT NOT NULL
        );
        CREATE TABLE experiments (
            experiment_id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER,
            name TEXT NOT NULL,
            type TEXT,
            timestamp TEXT NOT NULL,
            operator TEXT,
            notes TEXT,
            config_snapshot TEXT
        );
        CREATE TABLE spectra (
            spectrum_id INTEGER PRIMARY KEY AUTOINCREMENT,
            experiment_id INTEGER,
            type TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            wavelengths TEXT,
            intensities TEXT
        );
        CREATE TABLE analysis_results (
            result_id INTEGER PRIMARY KEY AUTOINCREMENT,
            experiment_id INTEGER,
            analysis_type TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            result_data TEXT,
            source_spectrum_ids TEXT
        );
        """
    )


def _columns(conn, table_name):
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table_name})")}


def test_database_p0_migrations_are_idempotent_and_register_soft_delete():
    conn = sqlite3.connect(":memory:")
    _create_legacy_schema(conn)

    first = run_migrations(conn, logger=lambda _message: None)
    second = run_migrations(conn, logger=lambda _message: None)

    assert "0002_snapshot_soft_delete" in first
    assert "0003_database_p0" in first
    assert second == []
    assert "is_active" in _columns(conn, "processing_snapshots")
    assert {"fingerprint", "description", "is_template"}.issubset(
        _columns(conn, "processing_snapshots")
    )
    assert {"processing_config_id", "parent_analysis_run_id", "run_kind"}.issubset(
        _columns(conn, "analysis_runs")
    )
    assert "source_spectrum_set_id" in _columns(conn, "spectrum_sets")
    assert "quality_check_results" in {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }


def test_processing_method_payload_is_canonical_and_fingerprint_stable():
    module = importlib.import_module("nanosense.core.processing_methods")

    first = module.build_processing_method(
        name="Routine",
        mode="Absorbance",
        parameters={"analysis_end_nm": 900, "analysis_start_nm": 500},
    )
    second = module.build_processing_method(
        name="Routine",
        mode="Absorbance",
        parameters={"analysis_start_nm": 500, "analysis_end_nm": 900},
    )

    assert first["parameters"] == second["parameters"]
    assert first["fingerprint"] == second["fingerprint"]
    assert len(first["fingerprint"]) == 64
    assert first["mode"] == "Absorbance"


def test_database_manager_creates_new_processing_method_version(tmp_path):
    database_manager = importlib.import_module("nanosense.core.database_manager")
    manager_class = database_manager.DatabaseManager
    manager_class._instance = None
    manager = manager_class(str(tmp_path / "p0.db"))

    try:
        first_id = manager.create_processing_method(
            name="Routine",
            mode="Absorbance",
            parameters={"analysis_start_nm": 500},
        )
        second_id = manager.create_processing_method(
            name="Routine",
            mode="Absorbance",
            parameters={"analysis_start_nm": 510},
            parent_config_id=first_id,
        )

        assert first_id is not None
        assert second_id is not None
        assert first_id != second_id
        second = manager.get_processing_method(second_id)
        assert second["parent_config_id"] == first_id
        assert second["parameters"]["analysis_start_nm"] == 510
        assert len(manager.list_processing_methods()) == 2
    finally:
        if manager.conn:
            manager.conn.close()
        manager_class._instance = None


def test_quality_control_marks_invalid_axis_and_nonfinite_values_as_fail():
    module = importlib.import_module("nanosense.core.quality_control")

    checks = module.run_quality_checks(
        [400.0, 401.0, 400.5],
        [0.1, float("nan"), 0.2],
        mode="Absorbance",
    )

    by_rule = {item["rule_key"]: item for item in checks}
    assert by_rule["wavelength_monotonic"]["severity"] == "fail"
    assert by_rule["finite_values"]["severity"] == "fail"
    assert module.summarize_quality(checks) == "fail"


def test_quality_control_warns_for_missing_reference_in_ratio_mode():
    module = importlib.import_module("nanosense.core.quality_control")

    checks = module.run_quality_checks(
        [400.0, 401.0, 402.0],
        [0.1, 0.2, 0.3],
        mode="Transmission",
        reference=None,
        background=[0.01, 0.01, 0.01],
    )

    by_rule = {item["rule_key"]: item for item in checks}
    assert by_rule["reference_required"]["severity"] == "warning"
    assert module.summarize_quality(checks) == "warning"


def test_save_spectrum_persists_quality_checks_and_summary(tmp_path):
    database_manager = importlib.import_module("nanosense.core.database_manager")
    manager_class = database_manager.DatabaseManager
    manager_class._instance = None
    manager = manager_class(str(tmp_path / "quality.db"))

    try:
        manager.conn.execute(
            "INSERT INTO projects (name, creation_date) VALUES (?, ?)",
            ("P0", "2026-08-20 15:00:00"),
        )
        manager.conn.commit()
        project_id = manager.conn.execute(
            "SELECT project_id FROM projects WHERE name = 'P0'"
        ).fetchone()[0]
        experiment_id = manager.create_experiment(
            project_id, "QC", "Absorbance", "2026-08-20 15:00:00"
        )
        spectrum_id = manager.save_spectrum(
            experiment_id,
            "Signal",
            "2026-08-20 15:00:01",
            [400.0, 401.0, 402.0],
            [0.1, float("nan"), 0.3],
            quality_context={"mode": "Absorbance"},
        )

        assert spectrum_id is not None
        row = manager.conn.execute(
            "SELECT quality_flag FROM spectrum_sets ORDER BY spectrum_set_id DESC LIMIT 1"
        ).fetchone()
        assert row[0] == "fail"
        count = manager.conn.execute(
            "SELECT COUNT(*) FROM quality_check_results"
        ).fetchone()[0]
        assert count >= 2
    finally:
        if manager.conn:
            manager.conn.close()
        manager_class._instance = None


def test_reanalysis_runs_are_append_only_and_keep_source_fingerprint(tmp_path):
    database_manager = importlib.import_module("nanosense.core.database_manager")
    manager_class = database_manager.DatabaseManager
    manager_class._instance = None
    manager = manager_class(str(tmp_path / "lineage.db"))

    try:
        project_id = manager.find_or_create_project("Lineage")
        experiment_id = manager.create_experiment(
            project_id, "Reanalysis", "Absorbance", "2026-08-20 15:00:00"
        )
        manager.save_spectrum(
            experiment_id,
            "Signal",
            "2026-08-20 15:00:01",
            [400.0, 401.0, 402.0],
            [0.1, 0.2, 0.3],
        )
        spectrum_set_id = manager.conn.execute(
            "SELECT spectrum_set_id FROM spectrum_sets ORDER BY spectrum_set_id DESC LIMIT 1"
        ).fetchone()[0]
        method_one = manager.create_processing_method(
            "Routine", "Absorbance", {"analysis_start_nm": 500}
        )
        method_two = manager.create_processing_method(
            "Routine", "Absorbance", {"analysis_start_nm": 510}, parent_config_id=method_one
        )

        first_run = manager.create_analysis_run(
            experiment_id,
            "peak_analysis",
            {"peak_wavelength": 610.0},
            processing_config_id=method_one,
            source_spectrum_set_ids=[spectrum_set_id],
        )
        second_run = manager.create_analysis_run(
            experiment_id,
            "peak_analysis",
            {"peak_wavelength": 611.0},
            processing_config_id=method_two,
            parent_analysis_run_id=first_run,
            source_spectrum_set_ids=[spectrum_set_id],
            run_kind="reanalysis",
        )

        assert first_run != second_run
        first = manager.get_analysis_run(first_run)
        second = manager.get_analysis_run(second_run)
        assert first["run_kind"] == "analysis"
        assert second["run_kind"] == "reanalysis"
        assert second["parent_analysis_run_id"] == first_run
        assert first["source_fingerprint"] == second["source_fingerprint"]
        assert second["processing_config_id"] == method_two
        assert manager.conn.execute(
            "SELECT COUNT(*) FROM analysis_runs WHERE experiment_id = ?",
            (experiment_id,),
        ).fetchone()[0] == 2
    finally:
        if manager.conn:
            manager.conn.close()
        manager_class._instance = None


def test_fresh_iteration_database_has_no_historical_records(tmp_path):
    database_manager = importlib.import_module("nanosense.core.database_manager")
    manager_class = database_manager.DatabaseManager
    manager_class._instance = None
    manager = manager_class(str(tmp_path / "empty_iteration.db"))

    try:
        tables = ("projects", "experiments", "spectrum_sets", "analysis_runs")
        counts = {
            table: manager.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in tables
        }
        assert counts == {table: 0 for table in tables}
    finally:
        if manager.conn:
            manager.conn.close()
        manager_class._instance = None


def test_explorer_can_read_structured_spectrum_with_provenance(tmp_path):
    database_manager = importlib.import_module("nanosense.core.database_manager")
    manager_class = database_manager.DatabaseManager
    manager_class._instance = None
    manager = manager_class(str(tmp_path / "payload.db"))

    try:
        project_id = manager.find_or_create_project("Explorer")
        experiment_id = manager.create_experiment(
            project_id, "Payload", "Absorbance", "2026-08-20 15:00:00"
        )
        manager.save_spectrum(
            experiment_id,
            "Signal",
            "2026-08-20 15:00:01",
            [400.0, 401.0],
            [0.1, 0.2],
            processing_info={"name": "Routine", "version": "1"},
        )
        spectrum_set_id = manager.conn.execute(
            "SELECT spectrum_set_id FROM spectrum_sets ORDER BY spectrum_set_id DESC LIMIT 1"
        ).fetchone()[0]

        from nanosense.core.data_access import ExplorerDataAccess

        payload = ExplorerDataAccess(manager.conn).fetch_spectrum_payload(spectrum_set_id)
        assert payload["x"].tolist() == [400.0, 401.0]
        assert payload["y"].tolist() == [0.1, 0.2]
        assert payload["metadata"]["spectrum_set_id"] == spectrum_set_id
        assert payload["metadata"]["processing_method"]["name"] == "Routine"
    finally:
        if manager.conn:
            manager.conn.close()
        manager_class._instance = None
