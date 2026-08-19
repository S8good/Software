from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
import math
from typing import Any, Dict, List, Optional


ERROR_INPUT_INVALID = "input_invalid"
ERROR_CONFIGURATION = "configuration_error"
ERROR_MODEL = "model_error"
ERROR_EXTERNAL_PROCESS = "external_process_error"
ERROR_REQUEST_TIMEOUT = "request_timeout"
ERROR_CANCELLED = "cancelled"


class LSPRValidationError(ValueError):
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.code = ERROR_INPUT_INVALID
        self.details = dict(details or {})


def _coerce_finite(value: Any, field: str, index: int) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        raise LSPRValidationError(
            f"{field}[{index}] must be numeric",
            {"field": field, "index": index, "reason": "not_numeric"},
        )
    if not math.isfinite(numeric):
        raise LSPRValidationError(
            f"{field}[{index}] must be finite",
            {"field": field, "index": index, "reason": "not_finite"},
        )
    return numeric


def validate_spectrum(wavelengths, intensities) -> None:
    try:
        wavelength_count = len(wavelengths)
        intensity_count = len(intensities)
    except TypeError:
        raise LSPRValidationError(
            "wavelengths and intensities must be sized sequences",
            {"reason": "not_sequence"},
        )

    if wavelength_count != intensity_count:
        raise LSPRValidationError(
            "wavelengths and intensities must have the same length",
            {
                "reason": "length_mismatch",
                "wavelength_count": wavelength_count,
                "intensity_count": intensity_count,
            },
        )
    if wavelength_count < 3:
        raise LSPRValidationError(
            "spectrum must contain at least 3 points",
            {"reason": "too_few_points", "point_count": wavelength_count},
        )

    normalized_wavelengths = [
        _coerce_finite(value, "wavelengths", index)
        for index, value in enumerate(wavelengths)
    ]
    for index in range(1, len(normalized_wavelengths)):
        if normalized_wavelengths[index] <= normalized_wavelengths[index - 1]:
            raise LSPRValidationError(
                "wavelengths must be strictly increasing",
                {"reason": "not_strictly_increasing", "index": index},
            )
    for index, value in enumerate(intensities):
        _coerce_finite(value, "intensities", index)


def validate_concentration(value: Any) -> None:
    numeric = _coerce_finite(value, "concentration_ng_ml", 0)
    if numeric < 0:
        raise LSPRValidationError(
            "concentration_ng_ml must be non-negative",
            {"field": "concentration_ng_ml", "reason": "negative"},
        )


def _json_compatible(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _json_compatible(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_compatible(item) for item in value]
    if hasattr(value, "tolist"):
        return value.tolist()
    return value


@dataclass
class ErrorResponse:
    code: str
    message: str
    details: Dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> Dict[str, Any]:
        return _json_compatible(asdict(self))


@dataclass
class PredictSingleRequest:
    wavelengths: List[float]
    intensities: List[float]
    model_mode: str = "auto"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> Dict[str, Any]:
        return _json_compatible(asdict(self))


@dataclass
class BuildComparisonRequest:
    wavelengths: List[float]
    intensities: List[float]
    model_mode: str = "auto"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> Dict[str, Any]:
        return _json_compatible(asdict(self))


@dataclass
class BuildDigitalTwinRequest:
    concentration_ng_ml: float
    experimental_wavelengths: Optional[List[float]] = None
    experimental_intensities: Optional[List[float]] = None
    model_mode: str = "auto"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> Dict[str, Any]:
        return _json_compatible(asdict(self))


@dataclass
class BatchPredictRequest:
    items: List[Dict[str, Any]]
    model_mode: str = "auto"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> Dict[str, Any]:
        return _json_compatible(asdict(self))


@dataclass
class HealthCheckResponse:
    ok: bool
    backend: str
    details: Dict[str, Any] = field(default_factory=dict)
    error: Optional[ErrorResponse] = None

    def to_payload(self) -> Dict[str, Any]:
        payload = _json_compatible(asdict(self))
        if self.error is None:
            payload["error"] = None
        return payload


@dataclass
class PredictionResponse:
    ok: bool
    backend: str
    model_mode: str
    predicted_concentration_ng_ml: Optional[float]
    report_mode: Optional[str]
    reported_text: Optional[str]
    uloq_ng_ml: Optional[float]
    super_quant_bin: Optional[str]
    metrics: Dict[str, Any] = field(default_factory=dict)
    error: Optional[ErrorResponse] = None

    def to_payload(self) -> Dict[str, Any]:
        payload = _json_compatible(asdict(self))
        if self.error is None:
            payload["error"] = None
        return payload


@dataclass
class ComparisonResponse:
    ok: bool
    backend: str
    model_mode: str
    wavelengths: List[float]
    input_spectrum: List[float]
    generated_spectrum: List[float]
    aligned_spectrum: List[float]
    physical_spectrum: Optional[List[float]] = None
    metrics: Dict[str, Any] = field(default_factory=dict)
    error: Optional[ErrorResponse] = None

    def to_payload(self) -> Dict[str, Any]:
        payload = _json_compatible(asdict(self))
        if self.error is None:
            payload["error"] = None
        return payload


@dataclass
class DigitalTwinResponse:
    ok: bool
    backend: str
    concentration_ng_ml: float
    wavelengths: List[float]
    baseline_spectrum: List[float]
    physical_spectrum: List[float]
    ai_spectrum: Optional[List[float]]
    metrics: Dict[str, Any] = field(default_factory=dict)
    error: Optional[ErrorResponse] = None

    def to_payload(self) -> Dict[str, Any]:
        payload = _json_compatible(asdict(self))
        if self.error is None:
            payload["error"] = None
        return payload


@dataclass
class BatchPredictionResponse:
    ok: bool
    backend: str
    rows: List[Dict[str, Any]]
    error: Optional[ErrorResponse] = None

    def to_payload(self) -> Dict[str, Any]:
        payload = _json_compatible(asdict(self))
        if self.error is None:
            payload["error"] = None
        return payload


class LSPRBackend(ABC):
    @abstractmethod
    def health_check(self) -> HealthCheckResponse:
        raise NotImplementedError

    @abstractmethod
    def predict_single(self, request: PredictSingleRequest) -> PredictionResponse:
        raise NotImplementedError

    @abstractmethod
    def build_comparison(self, request: BuildComparisonRequest) -> ComparisonResponse:
        raise NotImplementedError

    @abstractmethod
    def build_digital_twin(self, request: BuildDigitalTwinRequest) -> DigitalTwinResponse:
        raise NotImplementedError

    @abstractmethod
    def predict_batch(self, request: BatchPredictRequest) -> BatchPredictionResponse:
        raise NotImplementedError
