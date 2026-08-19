import math

import pytest

from nanosense.ml.paired_spectrum import (
    PairedSpectrumInput,
    PairedSpectrumValidationError,
    Spectrum,
)


def _pair(**overrides):
    payload = {
        "analyte_id": "cea",
        "chip_id": "chip-01",
        "site_id": "site-03",
        "reference_spectrum": Spectrum((500.0, 600.0, 700.0), (1.0, 2.0, 1.5)),
        "response_spectrum": Spectrum((500.0, 600.0, 700.0), (1.1, 2.2, 1.4)),
    }
    payload.update(overrides)
    return PairedSpectrumInput(**payload)


def test_valid_pair_has_stable_identity_and_payload():
    pair = _pair(nominal_concentration=5.0)

    assert pair.pair_id == "chip-01/site-03"
    assert pair.nominal_concentration == 5.0
    payload = pair.to_payload()
    assert payload["analyte_id"] == "cea"
    assert payload["reference_spectrum"]["intensities"] == [1.0, 2.0, 1.5]


@pytest.mark.parametrize(
    "field",
    ["chip_id", "site_id"],
)
def test_missing_pair_identity_is_rejected(field):
    with pytest.raises(PairedSpectrumValidationError) as exc_info:
        _pair(**{field: ""})

    assert exc_info.value.code == "pair_identity_missing"
    assert exc_info.value.details["field"] == field


def test_reference_and_response_must_share_a_wavelength_grid():
    with pytest.raises(PairedSpectrumValidationError) as exc_info:
        _pair(
            response_spectrum=Spectrum(
                (500.0, 601.0, 700.0), (1.1, 2.2, 1.4)
            )
        )

    assert exc_info.value.code == "wavelength_grid_mismatch"


@pytest.mark.parametrize(
    ("wavelengths", "intensities"),
    [
        ((500.0, 600.0), (1.0, 2.0)),
        ((500.0, 600.0, 550.0), (1.0, 2.0, 1.5)),
        ((500.0, 600.0, 700.0), (1.0, math.nan, 1.5)),
    ],
)
def test_spectrum_values_are_validated_before_pairing(wavelengths, intensities):
    with pytest.raises(PairedSpectrumValidationError):
        _pair(reference_spectrum=Spectrum(wavelengths, intensities))


def test_negative_nominal_concentration_is_rejected():
    with pytest.raises(PairedSpectrumValidationError) as exc_info:
        _pair(nominal_concentration=-1.0)

    assert exc_info.value.code == "concentration_invalid"
