from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any, Dict, Mapping, Optional, Tuple


class PairedSpectrumValidationError(ValueError):
    def __init__(self, code: str, message: str, details=None):
        super().__init__(message)
        self.code = code
        self.details = dict(details or {})


def _as_float_tuple(values, field_name: str) -> Tuple[float, ...]:
    try:
        converted = tuple(float(value) for value in values)
    except (TypeError, ValueError) as exc:
        raise PairedSpectrumValidationError(
            "spectrum_values_invalid",
            "%s must contain numeric values" % field_name,
            {"field": field_name},
        ) from exc
    if len(converted) < 3:
        raise PairedSpectrumValidationError(
            "spectrum_too_short",
            "%s must contain at least 3 points" % field_name,
            {"field": field_name, "point_count": len(converted)},
        )
    if not all(math.isfinite(value) for value in converted):
        raise PairedSpectrumValidationError(
            "spectrum_values_invalid",
            "%s must contain only finite values" % field_name,
            {"field": field_name, "reason": "not_finite"},
        )
    return converted


@dataclass(frozen=True)
class Spectrum:
    wavelengths: Tuple[float, ...]
    intensities: Tuple[float, ...]
    role: str = "unknown"
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        wavelengths = _as_float_tuple(self.wavelengths, "wavelengths")
        intensities = _as_float_tuple(self.intensities, "intensities")
        if len(wavelengths) != len(intensities):
            raise PairedSpectrumValidationError(
                "spectrum_length_mismatch",
                "wavelengths and intensities must have the same length",
                {"wavelength_count": len(wavelengths), "intensity_count": len(intensities)},
            )
        for index in range(1, len(wavelengths)):
            if wavelengths[index] <= wavelengths[index - 1]:
                raise PairedSpectrumValidationError(
                    "wavelengths_not_increasing",
                    "wavelengths must be strictly increasing",
                    {"index": index},
                )
        object.__setattr__(self, "wavelengths", wavelengths)
        object.__setattr__(self, "intensities", intensities)
        object.__setattr__(self, "metadata", dict(self.metadata or {}))

    def to_payload(self) -> Dict[str, Any]:
        return {
            "wavelengths": list(self.wavelengths),
            "intensities": list(self.intensities),
            "role": self.role,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class PairedSpectrumInput:
    analyte_id: str
    chip_id: str
    site_id: str
    reference_spectrum: Spectrum
    response_spectrum: Spectrum
    nominal_concentration: Optional[float] = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        for field_name in ("analyte_id", "chip_id", "site_id"):
            value = str(getattr(self, field_name) or "").strip()
            if not value:
                raise PairedSpectrumValidationError(
                    "pair_identity_missing",
                    "%s is required" % field_name,
                    {"field": field_name},
                )
            object.__setattr__(self, field_name, value)
        if not isinstance(self.reference_spectrum, Spectrum) or not isinstance(
            self.response_spectrum, Spectrum
        ):
            raise PairedSpectrumValidationError(
                "spectrum_missing",
                "reference_spectrum and response_spectrum are required Spectrum values",
            )
        if len(self.reference_spectrum.wavelengths) != len(self.response_spectrum.wavelengths):
            raise PairedSpectrumValidationError(
                "wavelength_grid_mismatch",
                "reference and response spectra must share a wavelength grid",
                {"reason": "length_mismatch"},
            )
        for index, (reference, response) in enumerate(
            zip(self.reference_spectrum.wavelengths, self.response_spectrum.wavelengths)
        ):
            if not math.isclose(reference, response, rel_tol=0.0, abs_tol=1e-6):
                raise PairedSpectrumValidationError(
                    "wavelength_grid_mismatch",
                    "reference and response spectra must share a wavelength grid",
                    {"index": index, "reference": reference, "response": response},
                )
        if self.nominal_concentration is not None:
            try:
                concentration = float(self.nominal_concentration)
            except (TypeError, ValueError) as exc:
                raise PairedSpectrumValidationError(
                    "concentration_invalid",
                    "nominal_concentration must be numeric",
                ) from exc
            if not math.isfinite(concentration) or concentration < 0:
                raise PairedSpectrumValidationError(
                    "concentration_invalid",
                    "nominal_concentration must be finite and non-negative",
                    {"value": self.nominal_concentration},
                )
            object.__setattr__(self, "nominal_concentration", concentration)
        object.__setattr__(self, "metadata", dict(self.metadata or {}))

    @property
    def pair_id(self) -> str:
        return "%s/%s" % (self.chip_id, self.site_id)

    def to_payload(self) -> Dict[str, Any]:
        return {
            "analyte_id": self.analyte_id,
            "chip_id": self.chip_id,
            "site_id": self.site_id,
            "reference_spectrum": self.reference_spectrum.to_payload(),
            "response_spectrum": self.response_spectrum.to_payload(),
            "nominal_concentration": self.nominal_concentration,
            "metadata": dict(self.metadata),
        }
