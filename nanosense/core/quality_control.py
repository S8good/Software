"""Deterministic, serializable spectrum quality checks."""

from typing import Any, Dict, Iterable, List, Optional

import numpy as np


_SEVERITY_ORDER = {"pass": 0, "warning": 1, "fail": 2}


def _finding(
    rule_key: str,
    severity: str,
    message: str,
    measured_value: Optional[float] = None,
    threshold_value: Optional[float] = None,
    unit: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return {
        "rule_key": rule_key,
        "severity": severity,
        "status": severity,
        "measured_value": measured_value,
        "threshold_value": threshold_value,
        "unit": unit,
        "message": message,
        "details": details or {},
    }


def run_quality_checks(
    wavelengths: Iterable[float],
    intensities: Iterable[float],
    *,
    mode: str = "Raw",
    background: Optional[Iterable[float]] = None,
    reference: Optional[Iterable[float]] = None,
    saturation_limit: float = 65535.0,
    low_signal_threshold: float = 1e-12,
) -> List[Dict[str, Any]]:
    """Return pass/warning/fail findings for one spectrum."""
    wavelength_array = np.asarray(list(wavelengths), dtype=float)
    intensity_array = np.asarray(list(intensities), dtype=float)
    checks: List[Dict[str, Any]] = []

    finite = bool(np.all(np.isfinite(wavelength_array)) and np.all(np.isfinite(intensity_array)))
    checks.append(
        _finding(
            "finite_values",
            "pass" if finite else "fail",
            "All wavelength and intensity values are finite."
            if finite
            else "The spectrum contains NaN or infinite values.",
        )
    )

    monotonic = len(wavelength_array) >= 2 and bool(np.all(np.diff(wavelength_array) > 0))
    checks.append(
        _finding(
            "wavelength_monotonic",
            "pass" if monotonic else "fail",
            "Wavelengths are strictly increasing."
            if monotonic
            else "Wavelengths must be strictly increasing.",
        )
    )

    finite_intensities = intensity_array[np.isfinite(intensity_array)]
    maximum = float(np.max(np.abs(finite_intensities))) if finite_intensities.size else None
    saturated = maximum is not None and maximum >= float(saturation_limit)
    checks.append(
        _finding(
            "saturation",
            "warning" if saturated else "pass",
            "Signal reaches the configured saturation limit."
            if saturated
            else "Signal is below the configured saturation limit.",
            measured_value=maximum,
            threshold_value=float(saturation_limit),
            unit="counts",
        )
    )

    low_signal = maximum is None or maximum <= float(low_signal_threshold)
    checks.append(
        _finding(
            "signal_level",
            "warning" if low_signal else "pass",
            "Signal level is too low for reliable analysis."
            if low_signal
            else "Signal level is above the minimum threshold.",
            measured_value=maximum,
            threshold_value=float(low_signal_threshold),
            unit="intensity",
        )
    )

    if mode in {"Reflectance", "Transmission", "Absorbance"}:
        missing_reference = reference is None
        checks.append(
            _finding(
                "reference_required",
                "warning" if missing_reference else "pass",
                "Reference spectrum is required for ratio processing."
                if missing_reference
                else "Reference spectrum is available.",
            )
        )
        missing_background = background is None
        checks.append(
            _finding(
                "background_required",
                "warning" if missing_background else "pass",
                "Background spectrum is required for ratio processing."
                if missing_background
                else "Background spectrum is available.",
            )
        )

    return checks


def summarize_quality(checks: Iterable[Dict[str, Any]]) -> str:
    severity = max(
        (item.get("severity", "pass") for item in checks),
        key=lambda value: _SEVERITY_ORDER.get(value, 2),
        default="pass",
    )
    return severity


__all__ = ["run_quality_checks", "summarize_quality"]
