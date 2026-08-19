from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import re
from typing import Dict, Iterable, List, Tuple, Union


ANALYTE_CEA = "cea"
ANALYTE_NSE = "nse"
ANALYTE_CYFRA21_1 = "cyfra21_1"
ANALYTE_PROGRP = "progrp"
ANALYTE_SCCA = "scca"
ANALYTE_P53 = "p53"
ANALYTE_CA125 = "ca125"
ANALYTE_TSGF = "tsgf"
ANALYTE_GAGE7 = "gage7"
ANALYTE_MAGE_A1 = "mage_a1"

STATUS_SUPPORTED = "supported"
STATUS_PLANNED = "planned"


class AnalyteRegistryError(ValueError):
    def __init__(self, code: str, message: str, details=None):
        super().__init__(message)
        self.code = code
        self.details = dict(details or {})


def _normalize_token(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value).strip().casefold())


@dataclass(frozen=True)
class AnalyteDefinition:
    analyte_id: str
    display_name: str
    aliases: Tuple[str, ...] = ()
    status: str = STATUS_PLANNED
    target_unit: str = "ng/mL"
    reference_state: str = "paired_reference"
    model_key: str = ""
    input_contract_version: str = "paired-lspr-v1"

    def __post_init__(self):
        if not self.analyte_id or _normalize_token(self.analyte_id) != self.analyte_id.replace("_", ""):
            raise ValueError("analyte_id must be a stable lowercase identifier")
        if self.status not in {STATUS_SUPPORTED, STATUS_PLANNED}:
            raise ValueError("status must be supported or planned")
        if not self.display_name.strip():
            raise ValueError("display_name must not be empty")

    @property
    def is_supported(self) -> bool:
        return self.status == STATUS_SUPPORTED


class AnalyteRegistry:
    def __init__(self, definitions: Iterable[AnalyteDefinition]):
        values = tuple(definitions)
        by_id: Dict[str, AnalyteDefinition] = {}
        by_token: Dict[str, AnalyteDefinition] = {}
        for definition in values:
            if definition.analyte_id in by_id:
                raise ValueError("duplicate analyte id: %s" % definition.analyte_id)
            by_id[definition.analyte_id] = definition
            names = (definition.analyte_id, definition.display_name) + tuple(definition.aliases)
            for name in names:
                token = _normalize_token(name)
                if not token:
                    raise ValueError("analyte aliases must not be empty")
                existing = by_token.get(token)
                if existing is not None and existing.analyte_id != definition.analyte_id:
                    raise ValueError("duplicate analyte alias: %s" % name)
                by_token[token] = definition
        self._definitions = values
        self._by_id = by_id
        self._by_token = by_token

    def all(self) -> Tuple[AnalyteDefinition, ...]:
        return self._definitions

    def supported(self) -> Tuple[AnalyteDefinition, ...]:
        return tuple(item for item in self._definitions if item.is_supported)

    def planned(self) -> Tuple[AnalyteDefinition, ...]:
        return tuple(item for item in self._definitions if not item.is_supported)

    def get(self, analyte_id: str) -> AnalyteDefinition:
        try:
            return self._by_id[analyte_id]
        except KeyError as exc:
            raise AnalyteRegistryError(
                "unknown_analyte",
                "Unknown analyte ID: %s" % analyte_id,
                {"value": analyte_id},
            ) from exc

    def resolve(self, value: Union[str, AnalyteDefinition]) -> AnalyteDefinition:
        if isinstance(value, AnalyteDefinition):
            return self.get(value.analyte_id)
        token = _normalize_token(value)
        definition = self._by_token.get(token)
        if definition is None:
            raise AnalyteRegistryError(
                "unknown_analyte",
                "Unknown analyte: %s" % value,
                {"value": value},
            )
        return definition


def _build_default_definitions() -> List[AnalyteDefinition]:
    return [
        AnalyteDefinition(
            ANALYTE_CEA,
            "CEA",
            ("carcinoembryonic antigen",),
            status=STATUS_SUPPORTED,
            model_key="cea_paired_reference_v1",
        ),
        AnalyteDefinition(ANALYTE_NSE, "NSE", ("neuron-specific enolase",)),
        AnalyteDefinition(
            ANALYTE_CYFRA21_1,
            "Cyfra21-1",
            ("cyfra21_1", "cyfra21-1"),
        ),
        AnalyteDefinition(
            ANALYTE_PROGRP,
            "ProGRP",
            ("ProGPR", "progrP", "progastrin-releasing peptide"),
        ),
        AnalyteDefinition(ANALYTE_SCCA, "SCCA", ("squamous cell carcinoma antigen",)),
        AnalyteDefinition(ANALYTE_P53, "p53", ("P53",)),
        AnalyteDefinition(ANALYTE_CA125, "CA125", ("CA-125",)),
        AnalyteDefinition(ANALYTE_TSGF, "TSGF"),
        AnalyteDefinition(ANALYTE_GAGE7, "GAGE-7", ("GAGE 7", "GAGE7")),
        AnalyteDefinition(ANALYTE_MAGE_A1, "MAGE-A1", ("MAGE A1", "MAGEA1")),
    ]


@lru_cache(maxsize=1)
def get_default_analyte_registry() -> AnalyteRegistry:
    return AnalyteRegistry(_build_default_definitions())
