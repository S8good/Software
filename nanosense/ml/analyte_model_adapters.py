from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
import json
from pathlib import Path
import subprocess
import sys
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional

from .analyte_registry import (
    ANALYTE_CEA,
    AnalyteDefinition,
    AnalyteRegistry,
    get_default_analyte_registry,
)
from .paired_spectrum import PairedSpectrumInput


class AnalyteModelError(RuntimeError):
    def __init__(self, code: str, message: str, details=None):
        super().__init__(message)
        self.code = code
        self.details = dict(details or {})


@dataclass(frozen=True)
class AdapterHealth:
    ok: bool
    code: str
    message: str
    details: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AnalyteModelMetadata:
    analyte_id: str
    model_key: str
    model_version: str
    input_contract_version: str
    status: str
    target_unit: str = "ng/mL"


@dataclass(frozen=True)
class AnalytePredictionResult:
    analyte_id: str
    predicted_concentration_ng_ml: Optional[float]
    predicted_log10_concentration: Optional[float]
    target_unit: str
    metrics: Mapping[str, Any] = field(default_factory=dict)
    qc: Mapping[str, Any] = field(default_factory=dict)
    provenance: Mapping[str, Any] = field(default_factory=dict)


class AnalyteModelAdapter(ABC):
    @abstractmethod
    def health_check(self) -> AdapterHealth:
        raise NotImplementedError

    @abstractmethod
    def validate_input(self, paired_input: PairedSpectrumInput) -> None:
        raise NotImplementedError

    @abstractmethod
    def predict_pair(
        self, paired_input: PairedSpectrumInput, options: Optional[Mapping[str, Any]] = None
    ) -> AnalytePredictionResult:
        raise NotImplementedError

    def predict_batch(
        self,
        paired_inputs: Iterable[PairedSpectrumInput],
        options: Optional[Mapping[str, Any]] = None,
    ) -> List[AnalytePredictionResult]:
        return [self.predict_pair(item, options=options) for item in paired_inputs]

    @abstractmethod
    def model_metadata(self) -> AnalyteModelMetadata:
        raise NotImplementedError


class UnavailableModelAdapter(AnalyteModelAdapter):
    def __init__(self, analyte_id: str, display_name: str):
        self.analyte_id = analyte_id
        self.display_name = display_name

    def health_check(self) -> AdapterHealth:
        return AdapterHealth(
            ok=False,
            code="model_not_implemented",
            message="Prediction model not supplied for %s." % self.display_name,
            details={"analyte_id": self.analyte_id},
        )

    def validate_input(self, paired_input: PairedSpectrumInput) -> None:
        if paired_input.analyte_id != self.analyte_id:
            raise AnalyteModelError(
                "analyte_mismatch",
                "Input analyte does not match this model adapter.",
                {"expected": self.analyte_id, "actual": paired_input.analyte_id},
            )

    def predict_pair(
        self, paired_input: PairedSpectrumInput, options: Optional[Mapping[str, Any]] = None
    ) -> AnalytePredictionResult:
        self.validate_input(paired_input)
        health = self.health_check()
        raise AnalyteModelError(health.code, health.message, health.details)

    def model_metadata(self) -> AnalyteModelMetadata:
        return AnalyteModelMetadata(
            analyte_id=self.analyte_id,
            model_key="",
            model_version="unavailable",
            input_contract_version="paired-lspr-v1",
            status="planned",
        )


class SubprocessCEAPredictor:
    """Invoke the optional py39 CEA runner through a small JSON protocol."""

    def __init__(self, config: Mapping[str, Any]):
        self.config = dict(config)
        self.runner_path = Path(str(self.config.get("lspr_cea_runner_path", ""))).expanduser()
        self.python_path = str(self.config.get("lspr_cea_runner_python", sys.executable))
        self.timeout_seconds = float(self.config.get("lspr_cea_runner_timeout", 30.0))

    def __call__(
        self, paired_input: PairedSpectrumInput, options: Mapping[str, Any]
    ) -> AnalytePredictionResult:
        request = {
            "operation": "predict_pair",
            "artifact": str(self.config.get("lspr_cea_model_artifact", "")),
            "input": paired_input.to_payload(),
            "options": dict(options or {}),
        }
        try:
            completed = subprocess.run(
                [self.python_path, str(self.runner_path)],
                input=json.dumps(request, ensure_ascii=False),
                text=True,
                capture_output=True,
                timeout=self.timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise AnalyteModelError(
                "request_timeout",
                "The CEA model runner timed out.",
                {"timeout_seconds": self.timeout_seconds},
            ) from exc
        except OSError as exc:
            raise AnalyteModelError(
                "external_process_error",
                "The CEA model runner could not be started.",
                {"exception_type": type(exc).__name__, "runner": str(self.runner_path)},
            ) from exc
        if completed.returncode != 0:
            raise AnalyteModelError(
                "external_process_error",
                "The CEA model runner returned a non-zero exit code.",
                {
                    "returncode": completed.returncode,
                    "stderr": completed.stderr.strip(),
                    "runner": str(self.runner_path),
                },
            )
        try:
            payload = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise AnalyteModelError(
                "external_process_error",
                "The CEA model runner returned invalid JSON.",
                {"stdout": completed.stdout[-1000:]},
            ) from exc
        if not isinstance(payload, Mapping) or payload.get("ok") is not True:
            error = payload.get("error", {}) if isinstance(payload, Mapping) else {}
            raise AnalyteModelError(
                str(error.get("code", "model_error")),
                str(error.get("message", "The CEA model runner rejected the request.")),
                error.get("details", {}),
            )
        result = payload.get("result")
        if not isinstance(result, Mapping):
            raise AnalyteModelError(
                "model_result_invalid",
                "The CEA model runner returned no result object.",
            )
        return AnalytePredictionResult(
            analyte_id=str(result.get("analyte_id", "")),
            predicted_concentration_ng_ml=result.get("predicted_concentration_ng_ml"),
            predicted_log10_concentration=result.get("predicted_log10_concentration"),
            target_unit=str(result.get("target_unit", "ng/mL")),
            metrics=dict(result.get("metrics", {})),
            qc=dict(result.get("qc", {})),
            provenance=dict(result.get("provenance", {})),
        )


class CEAPairedModelAdapter(AnalyteModelAdapter):
    """Paper-aligned CEA adapter shell.

    A predictor callable is injectable for tests and for the future trained model
    runner. Production construction requires a versioned artifact path and never
    falls back to the legacy single-spectrum engine.
    """

    def __init__(
        self,
        config: Optional[Mapping[str, Any]] = None,
        predictor: Optional[Callable[[PairedSpectrumInput, Mapping[str, Any]], AnalytePredictionResult]] = None,
    ):
        self.config = dict(config or {})
        self.predictor = predictor
        if self.predictor is None and self.config.get("lspr_cea_runner_path"):
            self.predictor = SubprocessCEAPredictor(self.config)

    def model_metadata(self) -> AnalyteModelMetadata:
        return AnalyteModelMetadata(
            analyte_id=ANALYTE_CEA,
            model_key="cea_paired_reference_v1",
            model_version=str(self.config.get("lspr_cea_model_version", "unavailable")),
            input_contract_version="paired-lspr-v1",
            status="supported",
        )

    def health_check(self) -> AdapterHealth:
        artifact_value = str(self.config.get("lspr_cea_model_artifact", "")).strip()
        if not artifact_value:
            return AdapterHealth(
                ok=False,
                code="model_artifact_unavailable",
                message="The paper-aligned CEA model artifact is not configured.",
                details={
                    "required_config": "lspr_cea_model_artifact",
                    "model_key": "cea_paired_reference_v1",
                },
            )
        artifact = Path(artifact_value).expanduser()
        if not artifact.is_file():
            return AdapterHealth(
                ok=False,
                code="model_artifact_unavailable",
                message="The configured CEA model artifact does not exist.",
                details={"artifact": str(artifact)},
            )
        if not bool(self.config.get("lspr_cea_model_enabled", False)):
            return AdapterHealth(
                ok=False,
                code="model_disabled",
                message="The CEA candidate model is disabled by configuration.",
                details={
                    "required_config": "lspr_cea_model_enabled",
                    "artifact": str(artifact),
                },
            )
        runner_value = str(self.config.get("lspr_cea_runner_path", "")).strip()
        if runner_value and not Path(runner_value).expanduser().is_file():
            return AdapterHealth(
                ok=False,
                code="model_runner_unavailable",
                message="The configured CEA model runner does not exist.",
                details={"runner": runner_value},
            )
        if self.predictor is None:
            return AdapterHealth(
                ok=False,
                code="model_runner_unavailable",
                message="The configured CEA artifact has no compatible model runner.",
                details={"artifact": str(artifact)},
            )
        return AdapterHealth(
            ok=True,
            code="ok",
            message="Paper-aligned CEA model is ready.",
            details={"artifact": str(artifact)},
        )

    def validate_input(self, paired_input: PairedSpectrumInput) -> None:
        if paired_input.analyte_id != ANALYTE_CEA:
            raise AnalyteModelError(
                "analyte_mismatch",
                "The CEA adapter accepts only CEA paired spectra.",
                {"expected": ANALYTE_CEA, "actual": paired_input.analyte_id},
            )
        if paired_input.reference_spectrum.role not in {"unknown", "reference"}:
            raise AnalyteModelError(
                "input_invalid",
                "The first spectrum must be a reference spectrum.",
                {"role": paired_input.reference_spectrum.role},
            )
        if paired_input.response_spectrum.role not in {"unknown", "response"}:
            raise AnalyteModelError(
                "input_invalid",
                "The second spectrum must be a response spectrum.",
                {"role": paired_input.response_spectrum.role},
            )

    def predict_pair(
        self, paired_input: PairedSpectrumInput, options: Optional[Mapping[str, Any]] = None
    ) -> AnalytePredictionResult:
        self.validate_input(paired_input)
        health = self.health_check()
        if not health.ok:
            raise AnalyteModelError(health.code, health.message, health.details)
        result = self.predictor(paired_input, dict(options or {}))
        if not isinstance(result, AnalytePredictionResult):
            raise AnalyteModelError(
                "model_result_invalid",
                "The CEA model runner returned an invalid result object.",
            )
        if result.analyte_id != ANALYTE_CEA:
            raise AnalyteModelError(
                "model_result_invalid",
                "The CEA model runner returned a result for another analyte.",
                {"actual": result.analyte_id},
            )
        return result


def build_default_analyte_adapters(
    config: Optional[Mapping[str, Any]] = None,
    registry: Optional[AnalyteRegistry] = None,
) -> Dict[str, AnalyteModelAdapter]:
    registry = registry or get_default_analyte_registry()
    adapters: Dict[str, AnalyteModelAdapter] = {
        ANALYTE_CEA: CEAPairedModelAdapter(config),
    }
    for definition in registry.planned():
        adapters[definition.analyte_id] = UnavailableModelAdapter(
            definition.analyte_id, definition.display_name
        )
    return adapters
