"""Canonical processing-method payloads used by the database and GUI."""

import hashlib
import json
from typing import Any, Dict, Optional


def _normalize(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _normalize(value[key]) for key in sorted(value)}
    if isinstance(value, (list, tuple)):
        return [_normalize(item) for item in value]
    if hasattr(value, "item"):
        return _normalize(value.item())
    return value


def build_processing_method(
    name: str,
    mode: str,
    parameters: Dict[str, Any],
    version: str = "1.0",
    description: str = "",
    parent_config_id: Optional[int] = None,
    is_template: bool = True,
) -> Dict[str, Any]:
    name = str(name or "").strip()
    mode = str(mode or "").strip()
    if not name:
        raise ValueError("processing method name is required")
    if not mode:
        raise ValueError("processing method mode is required")
    normalized_parameters = _normalize(dict(parameters or {}))
    identity = {
        "name": name,
        "mode": mode,
        "version": str(version or "1.0"),
        "parameters": normalized_parameters,
    }
    serialized = json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return {
        **identity,
        "description": str(description or ""),
        "parent_config_id": parent_config_id,
        "is_template": bool(is_template),
        "fingerprint": hashlib.sha256(serialized.encode("utf-8")).hexdigest(),
    }


__all__ = ["build_processing_method"]
