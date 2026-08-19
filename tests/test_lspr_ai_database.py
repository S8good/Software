from pathlib import Path
import sqlite3
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from nanosense.core.database_manager import DatabaseManager
import json


def _fresh_manager(db_path):
    DatabaseManager._instance = None
    manager = DatabaseManager(str(db_path))
    return manager


def test_save_lspr_ai_prediction_creates_analysis_run_and_metrics(tmp_path):
    db_path = tmp_path / "lspr.db"
    manager = _fresh_manager(db_path)
    project_id = manager.find_or_create_project("Demo")
    experiment_id = manager.create_experiment(project_id, "Exp 1", "LSPR", "2025-01-01 10:00:00")

    analysis_run_id = manager.save_lspr_ai_prediction(
        experiment_id=experiment_id,
        metrics={
            "predicted_concentration_ng_ml": 12.34,
            "report_mode": "quantitative",
            "reported_text": "12.3400 ng/ml",
            "peak_wavelength_nm": 612.5,
            "delta_lambda_nm": 2.5,
        },
        input_context={
            "model_mode": "v2",
            "lspr_backend_mode": "subprocess",
            "source_type": "file_import",
            "source_file": "demo.csv",
        },
    )

    assert analysis_run_id is not None

    row = manager.conn.execute(
        "SELECT analysis_type, input_context FROM analysis_runs WHERE analysis_run_id = ?",
        (analysis_run_id,),
    ).fetchone()
    assert row[0] == "lspr_ai_prediction"
    assert '"model_mode": "v2"' in row[1]

    metrics = dict(
        manager.conn.execute(
            "SELECT metric_key, metric_value FROM analysis_metrics WHERE analysis_run_id = ?",
            (analysis_run_id,),
        ).fetchall()
    )
    assert metrics["predicted_concentration_ng_ml"] == "12.34"
    assert metrics["report_mode"] == "quantitative"


def test_save_lspr_ai_prediction_returns_none_for_missing_connection(tmp_path):
    db_path = tmp_path / "lspr.db"
    manager = _fresh_manager(db_path)
    manager.close()

    result = manager.save_lspr_ai_prediction(
        experiment_id=1,
        metrics={"predicted_concentration_ng_ml": 1.23},
        input_context={"model_mode": "auto"},
    )

    assert result is None


def test_save_lspr_ai_prediction_derives_algorithm_version_and_preserves_provenance(tmp_path):
    db_path = tmp_path / "lspr-provenance.db"
    manager = _fresh_manager(db_path)
    project_id = manager.find_or_create_project("Provenance Demo")
    experiment_id = manager.create_experiment(project_id, "Exp 1", "LSPR", "2025-01-01 10:00:00")

    analysis_run_id = manager.save_lspr_ai_prediction(
        experiment_id=experiment_id,
        metrics={"predicted_concentration_ng_ml": 3.21},
        input_context={
            "model_mode": "v2",
            "provenance": {
                "backend": "stub",
                "requested_at": "2026-08-19T00:00:00+00:00",
                "metadata": {"source": "unit-test"},
            },
        },
    )

    row = manager.conn.execute(
        "SELECT algorithm_version, input_context FROM analysis_runs WHERE analysis_run_id = ?",
        (analysis_run_id,),
    ).fetchone()

    assert row[0] == "v2"
    context = json.loads(row[1])
    assert context["provenance"]["backend"] == "stub"
    assert context["provenance"]["metadata"]["source"] == "unit-test"


def test_save_lspr_ai_prediction_marks_paired_context_and_preserves_pair_links(tmp_path):
    db_path = tmp_path / "lspr-paired.db"
    manager = _fresh_manager(db_path)
    project_id = manager.find_or_create_project("Paired Demo")
    experiment_id = manager.create_experiment(project_id, "Exp 1", "LSPR", "2025-01-01 10:00:00")

    analysis_run_id = manager.save_lspr_ai_prediction(
        experiment_id=experiment_id,
        metrics={"predicted_concentration_ng_ml": 4.2},
        input_context={
            "analyte_id": "cea",
            "chip_id": "chip-01",
            "site_id": "site-03",
            "reference_spectrum_id": 11,
            "response_spectrum_id": 12,
            "pairing_status": "validated",
            "preprocessing_version": "cea-paper-v1",
            "model_key": "cea_paired_reference_v1",
            "model_version": "test-model",
        },
    )

    context = json.loads(
        manager.conn.execute(
            "SELECT input_context FROM analysis_runs WHERE analysis_run_id = ?",
            (analysis_run_id,),
        ).fetchone()[0]
    )
    assert context["workflow"] == "paper_paired_reference"
    assert context["analyte_id"] == "cea"
    assert context["reference_spectrum_id"] == 11
    assert context["response_spectrum_id"] == 12


def test_save_lspr_ai_prediction_marks_old_single_spectrum_context_as_legacy(tmp_path):
    db_path = tmp_path / "lspr-legacy.db"
    manager = _fresh_manager(db_path)
    project_id = manager.find_or_create_project("Legacy Demo")
    experiment_id = manager.create_experiment(project_id, "Exp 1", "LSPR", "2025-01-01 10:00:00")

    analysis_run_id = manager.save_lspr_ai_prediction(
        experiment_id=experiment_id,
        metrics={"predicted_concentration_ng_ml": 1.2},
        input_context={"model_mode": "auto"},
    )

    context = json.loads(
        manager.conn.execute(
            "SELECT input_context FROM analysis_runs WHERE analysis_run_id = ?",
            (analysis_run_id,),
        ).fetchone()[0]
    )
    assert context["workflow"] == "legacy_generic"
