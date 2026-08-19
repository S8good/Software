from pathlib import Path
import sys

import pytest

from nanosense.ml.analyte_model_adapters import (
    AnalytePredictionResult,
    CEAPairedModelAdapter,
    UnavailableModelAdapter,
)
from nanosense.ml.paired_spectrum import PairedSpectrumInput, Spectrum


def _pair(analyte_id="cea"):
    spectrum = Spectrum((500.0, 600.0, 700.0), (1.0, 2.0, 1.5))
    response = Spectrum((500.0, 600.0, 700.0), (1.1, 2.2, 1.4))
    return PairedSpectrumInput(analyte_id, "chip-01", "site-01", spectrum, response)


def test_planned_analyte_adapter_is_explicitly_unavailable():
    adapter = UnavailableModelAdapter("nse", "NSE")

    health = adapter.health_check()
    assert health.ok is False
    assert health.code == "model_not_implemented"

    with pytest.raises(Exception) as exc_info:
        adapter.predict_pair(_pair("nse"))
    assert exc_info.value.code == "model_not_implemented"


def test_cea_adapter_requires_a_versioned_artifact_before_prediction(tmp_path: Path):
    adapter = CEAPairedModelAdapter({})

    health = adapter.health_check()
    assert health.ok is False
    assert health.code == "model_artifact_unavailable"

    with pytest.raises(Exception) as exc_info:
        adapter.predict_pair(_pair())
    assert exc_info.value.code == "model_artifact_unavailable"
    assert "lspr_cea_model_artifact" in exc_info.value.details["required_config"]


def test_cea_adapter_does_not_accept_a_different_analyte(tmp_path: Path):
    artifact = tmp_path / "cea-model.json"
    artifact.write_text("{}", encoding="utf-8")
    adapter = CEAPairedModelAdapter({"lspr_cea_model_artifact": str(artifact)})

    with pytest.raises(Exception) as exc_info:
        adapter.predict_pair(_pair("nse"))
    assert exc_info.value.code == "analyte_mismatch"


def test_cea_candidate_is_disabled_without_explicit_enable(tmp_path: Path):
    artifact = tmp_path / "cea-model.json"
    artifact.write_text("{}", encoding="utf-8")
    adapter = CEAPairedModelAdapter(
        {"lspr_cea_model_artifact": str(artifact)},
        predictor=lambda paired_input, options: AnalytePredictionResult(
            analyte_id="cea",
            predicted_concentration_ng_ml=1.0,
            predicted_log10_concentration=0.0,
            target_unit="ng/mL",
        ),
    )

    health = adapter.health_check()
    assert health.ok is False
    assert health.code == "model_disabled"


def test_cea_candidate_requires_explicit_enable_before_prediction(tmp_path: Path):
    artifact = tmp_path / "cea-model.json"
    artifact.write_text("{}", encoding="utf-8")
    adapter = CEAPairedModelAdapter(
        {
            "lspr_cea_model_artifact": str(artifact),
            "lspr_cea_model_enabled": True,
        },
        predictor=lambda paired_input, options: AnalytePredictionResult(
            analyte_id="cea",
            predicted_concentration_ng_ml=1.0,
            predicted_log10_concentration=0.0,
            target_unit="ng/mL",
        ),
    )

    health = adapter.health_check()
    assert health.ok is True
    result = adapter.predict_pair(_pair())
    assert result.predicted_concentration_ng_ml == 1.0


def test_cea_candidate_can_use_explicit_json_runner(tmp_path: Path):
    artifact = tmp_path / "manifest.json"
    artifact.write_text("{}", encoding="utf-8")
    runner = tmp_path / "runner.py"
    runner.write_text(
        "import json, sys\n"
        "request = json.load(sys.stdin)\n"
        "assert request['operation'] == 'predict_pair'\n"
        "print(json.dumps({'ok': True, 'result': {"
        "'analyte_id': 'cea', 'predicted_concentration_ng_ml': 2.5,"
        "'predicted_log10_concentration': 0.398, 'target_unit': 'ng/mL',"
        "'metrics': {}, 'qc': {'runner': 'test'}, 'provenance': {}}}))\n",
        encoding="utf-8",
    )
    adapter = CEAPairedModelAdapter(
        {
            "lspr_cea_model_artifact": str(artifact),
            "lspr_cea_model_enabled": True,
            "lspr_cea_runner_path": str(runner),
            "lspr_cea_runner_python": sys.executable,
        }
    )

    health = adapter.health_check()
    assert health.ok is True
    result = adapter.predict_pair(_pair())
    assert result.predicted_concentration_ng_ml == 2.5
    assert result.qc["runner"] == "test"
