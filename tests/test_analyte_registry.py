import pytest

from nanosense.ml.analyte_registry import (
    ANALYTE_CEA,
    ANALYTE_PROGRP,
    AnalyteRegistryError,
    get_default_analyte_registry,
)


def test_default_registry_contains_the_ten_paper_analytes():
    registry = get_default_analyte_registry()

    assert [item.analyte_id for item in registry.all()] == [
        "cea",
        "nse",
        "cyfra21_1",
        "progrp",
        "scca",
        "p53",
        "ca125",
        "tsgf",
        "gage7",
        "mage_a1",
    ]
    assert registry.get(ANALYTE_CEA).status == "supported"
    assert registry.get(ANALYTE_PROGRP).display_name == "ProGRP"
    assert [item.analyte_id for item in registry.planned()] == [
        "nse",
        "cyfra21_1",
        "progrp",
        "scca",
        "p53",
        "ca125",
        "tsgf",
        "gage7",
        "mage_a1",
    ]


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("CEA", "cea"),
        ("carcinoembryonic antigen", "cea"),
        ("Cyfra21-1", "cyfra21_1"),
        ("ProGPR", "progrp"),
        ("ProGRP", "progrp"),
        ("GAGE 7", "gage7"),
        ("MAGE A1", "mage_a1"),
    ],
)
def test_registry_resolves_display_names_and_aliases(value, expected):
    registry = get_default_analyte_registry()
    assert registry.resolve(value).analyte_id == expected


def test_unknown_analyte_is_a_structured_configuration_error():
    with pytest.raises(AnalyteRegistryError) as exc_info:
        get_default_analyte_registry().resolve("unknown-marker")

    assert exc_info.value.code == "unknown_analyte"
    assert exc_info.value.details["value"] == "unknown-marker"
