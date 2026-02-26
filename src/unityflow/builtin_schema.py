from __future__ import annotations

import json
from pathlib import Path

_SCHEMA_PATH = Path(__file__).parent / "data" / "builtin_schemas.json"

_schemas: dict[int, frozenset[str]] | None = None
_common_meta: frozenset[str] = frozenset()


def _load() -> None:
    global _schemas, _common_meta
    with open(_SCHEMA_PATH, encoding="utf-8") as f:
        raw = json.load(f)

    _common_meta = frozenset(raw.pop("_common_meta", []))
    _schemas = {}
    for class_id_str, fields in raw.items():
        _schemas[int(class_id_str)] = frozenset(fields) | _common_meta


def get_builtin_fields(class_id: int) -> frozenset[str] | None:
    global _schemas
    if _schemas is None:
        _load()
    assert _schemas is not None
    return _schemas.get(class_id)
