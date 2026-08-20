from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import wraps
import logging
from pathlib import Path
import time
from typing import Any, Dict, List, Optional

from .lspr_backend_factory import create_lspr_backend
from .lspr_backend_protocol import (
    BatchPredictRequest,
    BuildComparisonRequest,
    BuildDigitalTwinRequest,
    ComparisonResponse,
    DigitalTwinResponse,
    LSPRBackend,
    PredictSingleRequest,
    PredictionResponse,
    LSPRValidationError,
    validate_concentration,
    validate_spectrum,
)
from .lspr_master_bridge import LSPRMasterBridge
from .analyte_model_adapters import (
    AnalyteModelError,
    AnalyteModelAdapter,
    AnalytePredictionResult,
    build_default_analyte_adapters,
)
from .analyte_registry import AnalyteRegistryError, get_default_analyte_registry
from .paired_spectrum import PairedSpectrumInput, PairedSpectrumValidationError
from nanosense.utils.logging_config import (
    current_context,
    get_logger,
    logging_context,
    new_correlation_id,
)


logger = get_logger(__name__)


def _context_extra(session_id, correlation_id):
    return {"session_id": session_id, "correlation_id": correlation_id}


def _log_operation(operation):
    def decorator(function):
        @wraps(function)
        def wrapped(self, *args, **kwargs):
            session_id = current_context()["session_id"]
            correlation_id = new_correlation_id("lspr")
            extra = _context_extra(session_id, correlation_id)
            started = time.monotonic()
            with logging_context(
                session_id=session_id,
                correlation_id=correlation_id,
            ):
                logger.info(
                    "lspr_started event=lspr_started operation=%s",
                    operation,
                    extra=extra,
                )
                try:
                    result = function(self, *args, **kwargs)
                except Exception:
                    logger.exception(
                        "lspr_failed event=lspr_failed operation=%s",
                        operation,
                        extra=extra,
                    )
                    raise
                finally:
                    logger.info(
                        "lspr_finished event=lspr_finished operation=%s duration_ms=%.1f",
                        operation,
                        (time.monotonic() - started) * 1000.0,
                        extra=extra,
                    )
            return result

        return wrapped

    return decorator


class LSPRAIServiceError(RuntimeError):
    def __init__(self, code: str, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.code = code
        self.details = dict(details or {})


@dataclass
class LSPRPredictionResult:
    predicted_concentration_ng_ml: float
    report_mode: str
    reported_text: str
    uloq_ng_ml: Optional[float]
    super_quant_bin: Optional[str]
    metrics: Dict[str, Any]
    backend: str
    model_mode: str
    provenance: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LSPRSpectrumComparisonResult:
    wavelengths: List[float]
    input_spectrum: List[float]
    generated_spectrum: List[float]
    aligned_spectrum: List[float]
    physical_spectrum: Optional[List[float]]
    metrics: Dict[str, Any]
    backend: str
    model_mode: str
    provenance: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LSPRDigitalTwinResult:
    concentration_ng_ml: float
    wavelengths: List[float]
    baseline_spectrum: List[float]
    physical_spectrum: List[float]
    ai_spectrum: Optional[List[float]]
    metrics: Dict[str, Any]
    backend: str
    provenance: Dict[str, Any] = field(default_factory=dict)


class LSPRAIService:
    def __init__(
        self,
        backend: Optional[LSPRBackend] = None,
        config: Optional[Dict[str, Any]] = None,
        analyte_registry=None,
        analyte_adapters: Optional[Dict[str, AnalyteModelAdapter]] = None,
    ):
        self.config = config or {}
        self.backend = backend or create_lspr_backend(self.config)
        self.analyte_registry = analyte_registry or get_default_analyte_registry()
        self.analyte_adapters = build_default_analyte_adapters(
            self.config, registry=self.analyte_registry
        )
        if analyte_adapters:
            self.analyte_adapters.update(analyte_adapters)

    @staticmethod
    def _raise_if_error(response) -> None:
        if getattr(response, 'ok', False):
            return
        error = getattr(response, 'error', None)
        if error is not None:
            raise LSPRAIServiceError(
                error.code,
                error.message,
                getattr(error, "details", {}),
            )
        raise LSPRAIServiceError("model_error", "LSPR backend request failed")

    @staticmethod
    def _validate_spectrum(wavelengths, intensities) -> None:
        try:
            validate_spectrum(wavelengths, intensities)
        except LSPRValidationError as exc:
            raise LSPRAIServiceError(exc.code, str(exc), exc.details) from exc

    @staticmethod
    def _validate_concentration(concentration_ng_ml: float) -> None:
        try:
            validate_concentration(concentration_ng_ml)
        except LSPRValidationError as exc:
            raise LSPRAIServiceError(exc.code, str(exc), exc.details) from exc

    @staticmethod
    def _build_provenance(model_mode: str, backend: str, metadata: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        return {
            "model_mode": model_mode,
            "backend": backend,
            "requested_at": datetime.now(timezone.utc).isoformat(),
            "metadata": dict(metadata or {}),
        }

    def validate_paired_input(self, paired_input: PairedSpectrumInput):
        if not isinstance(paired_input, PairedSpectrumInput):
            raise LSPRAIServiceError(
                "input_invalid",
                "predict_paired requires a PairedSpectrumInput value",
            )
        try:
            definition = self.analyte_registry.resolve(paired_input.analyte_id)
            adapter = self.analyte_adapters.get(definition.analyte_id)
            if adapter is None:
                raise LSPRAIServiceError(
                    "configuration_error",
                    "No model adapter is registered for %s" % definition.display_name,
                    {"analyte_id": definition.analyte_id},
                )
            adapter.validate_input(paired_input)
            return definition
        except AnalyteRegistryError as exc:
            raise LSPRAIServiceError(exc.code, str(exc), exc.details) from exc
        except PairedSpectrumValidationError as exc:
            raise LSPRAIServiceError(exc.code, str(exc), exc.details) from exc
        except AnalyteModelError as exc:
            raise LSPRAIServiceError(exc.code, str(exc), exc.details) from exc

    @_log_operation("predict_paired")
    def predict_paired(
        self,
        paired_input: PairedSpectrumInput,
        options: Optional[Dict[str, Any]] = None,
    ) -> AnalytePredictionResult:
        definition = self.validate_paired_input(paired_input)
        adapter = self.analyte_adapters[definition.analyte_id]
        try:
            result = adapter.predict_pair(paired_input, options=options)
        except AnalyteModelError as exc:
            raise LSPRAIServiceError(exc.code, str(exc), exc.details) from exc
        if not isinstance(result, AnalytePredictionResult):
            raise LSPRAIServiceError(
                "model_result_invalid",
                "The analyte model returned an invalid prediction result",
                {"analyte_id": definition.analyte_id},
            )
        return result

    @_log_operation("discover_model_modes")
    def discover_model_modes(self) -> List[str]:
        root = self.config.get('lspr_master_root')
        try:
            bridge = LSPRMasterBridge(Path(root) if root else None)
            return bridge.list_available_model_modes()
        except Exception:
            logger.exception(
                "event=lspr_model_mode_discovery_failed fallback=auto"
            )
            return ['auto']

    @_log_operation("predict_single_spectrum")
    def predict_single_spectrum(self, wavelengths: List[float], intensities: List[float], model_mode: str = 'auto', metadata: Optional[Dict[str, Any]] = None) -> LSPRPredictionResult:
        self._validate_spectrum(wavelengths, intensities)
        response: PredictionResponse = self.backend.predict_single(
            PredictSingleRequest(wavelengths=list(wavelengths), intensities=list(intensities), model_mode=model_mode, metadata=metadata or {})
        )
        self._raise_if_error(response)
        return LSPRPredictionResult(
            predicted_concentration_ng_ml=float(response.predicted_concentration_ng_ml),
            report_mode=str(response.report_mode),
            reported_text=str(response.reported_text),
            uloq_ng_ml=response.uloq_ng_ml,
            super_quant_bin=response.super_quant_bin,
            metrics=dict(response.metrics),
            backend=response.backend,
            model_mode=response.model_mode,
            provenance=self._build_provenance(response.model_mode, response.backend, metadata),
        )

    @_log_operation("build_spectrum_comparison")
    def build_spectrum_comparison(self, wavelengths: List[float], intensities: List[float], model_mode: str = 'auto', metadata: Optional[Dict[str, Any]] = None) -> LSPRSpectrumComparisonResult:
        self._validate_spectrum(wavelengths, intensities)
        response: ComparisonResponse = self.backend.build_comparison(
            BuildComparisonRequest(wavelengths=list(wavelengths), intensities=list(intensities), model_mode=model_mode, metadata=metadata or {})
        )
        self._raise_if_error(response)
        return LSPRSpectrumComparisonResult(
            wavelengths=list(response.wavelengths),
            input_spectrum=list(response.input_spectrum),
            generated_spectrum=list(response.generated_spectrum),
            aligned_spectrum=list(response.aligned_spectrum),
            physical_spectrum=list(response.physical_spectrum) if response.physical_spectrum is not None else None,
            metrics=dict(response.metrics),
            backend=response.backend,
            model_mode=response.model_mode,
            provenance=self._build_provenance(response.model_mode, response.backend, metadata),
        )

    @_log_operation("build_digital_twin_context")
    def build_digital_twin_context(self, concentration_ng_ml: float, experimental_wavelengths: Optional[List[float]] = None, experimental_intensities: Optional[List[float]] = None, model_mode: str = 'auto', metadata: Optional[Dict[str, Any]] = None) -> LSPRDigitalTwinResult:
        self._validate_concentration(concentration_ng_ml)
        if (experimental_wavelengths is None) != (experimental_intensities is None):
            raise LSPRAIServiceError(
                "input_invalid",
                "experimental_wavelengths and experimental_intensities must be provided together",
                {"reason": "incomplete_experimental_spectrum"},
            )
        if experimental_wavelengths is not None and experimental_intensities is not None:
            self._validate_spectrum(experimental_wavelengths, experimental_intensities)
        response: DigitalTwinResponse = self.backend.build_digital_twin(
            BuildDigitalTwinRequest(
                concentration_ng_ml=float(concentration_ng_ml),
                experimental_wavelengths=list(experimental_wavelengths) if experimental_wavelengths is not None else None,
                experimental_intensities=list(experimental_intensities) if experimental_intensities is not None else None,
                model_mode=model_mode,
                metadata=metadata or {},
            )
        )
        self._raise_if_error(response)
        return LSPRDigitalTwinResult(
            concentration_ng_ml=float(response.concentration_ng_ml),
            wavelengths=list(response.wavelengths),
            baseline_spectrum=list(response.baseline_spectrum),
            physical_spectrum=list(response.physical_spectrum),
            ai_spectrum=list(response.ai_spectrum) if response.ai_spectrum is not None else None,
            metrics=dict(response.metrics),
            backend=response.backend,
            provenance=self._build_provenance(model_mode, response.backend, metadata),
        )

    @_log_operation("compare_models")
    def compare_models(self, wavelengths: List[float], intensities: List[float], model_modes: Optional[List[str]] = None, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        modes = list(model_modes or self.discover_model_modes())
        rows = []
        comparisons = []
        for mode in modes:
            prediction = self.predict_single_spectrum(wavelengths, intensities, model_mode=mode, metadata=metadata)
            comparison = self.build_spectrum_comparison(wavelengths, intensities, model_mode=mode, metadata=metadata)
            rows.append({
                'model_mode': mode,
                'predicted_concentration_ng_ml': prediction.predicted_concentration_ng_ml,
                'report_mode': prediction.report_mode,
                'reported_text': prediction.reported_text,
                'backend': prediction.backend,
            })
            comparisons.append(comparison)
        return {'rows': rows, 'comparisons': comparisons}

    @_log_operation("predict_batch")
    def predict_batch(self, items: List[Dict[str, Any]], model_mode: str = 'auto', metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if not items:
            raise LSPRAIServiceError("input_invalid", "batch items must not be empty", {"reason": "empty_batch"})
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                raise LSPRAIServiceError(
                    "input_invalid",
                    f"batch item {index} must be an object",
                    {"index": index, "reason": "invalid_item"},
                )
            wavelengths = item.get("wavelengths")
            intensities = item.get("intensities")
            if wavelengths is None and intensities is None:
                if not item.get("file_path"):
                    raise LSPRAIServiceError(
                        "input_invalid",
                        f"batch item {index} has no spectrum source",
                        {"index": index, "reason": "missing_spectrum_source"},
                    )
                continue
            try:
                self._validate_spectrum(wavelengths, intensities)
            except LSPRAIServiceError as exc:
                details = dict(exc.details)
                details["index"] = index
                raise LSPRAIServiceError(exc.code, str(exc), details) from exc
        response = self.backend.predict_batch(BatchPredictRequest(items=list(items), model_mode=model_mode, metadata=metadata or {}))
        self._raise_if_error(response)
        return {
            'rows': list(response.rows),
            'backend': response.backend,
            'provenance': self._build_provenance(model_mode, response.backend, metadata),
        }
