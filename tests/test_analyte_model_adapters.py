from pathlib import Path

import pytest

from nanosense.ml.analyte_model_adapters import (
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
