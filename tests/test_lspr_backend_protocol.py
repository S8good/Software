from pathlib import Path
import sys

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import nanosense.ml.lspr_backend_protocol as protocol


LSPRValidationError = getattr(protocol, "LSPRValidationError", ValueError)
validate_spectrum = getattr(protocol, "validate_spectrum", lambda *_args, **_kwargs: None)
validate_concentration = getattr(protocol, "validate_concentration", lambda *_args, **_kwargs: None)


def test_validate_spectrum_accepts_three_point_increasing_finite_arrays():
    assert validate_spectrum([500.0, 501.0, 502.0], [0.1, 0.2, 0.3]) is None


@pytest.mark.parametrize(
    "wavelengths, intensities",
    [
        ([], []),
        ([500.0, 501.0], [0.1]),
        ([500.0, 501.0], [0.1, 0.2]),
        ([500.0, float("nan"), 502.0], [0.1, 0.2, 0.3]),
        ([500.0, 499.0, 502.0], [0.1, 0.2, 0.3]),
        ([500.0, 501.0, 502.0], [0.1, float("inf"), 0.3]),
    ],
)
def test_validate_spectrum_rejects_invalid_arrays(wavelengths, intensities):
    with pytest.raises(LSPRValidationError) as exc_info:
        validate_spectrum(wavelengths, intensities)

    assert exc_info.value.code == "input_invalid"
    assert exc_info.value.details


def test_validate_concentration_rejects_negative_and_non_finite_values():
    for value in (-1.0, float("nan"), float("inf")):
        with pytest.raises(LSPRValidationError) as exc_info:
            validate_concentration(value)

        assert exc_info.value.code == "input_invalid"


def test_validate_concentration_accepts_zero():
    assert validate_concentration(0.0) is None
