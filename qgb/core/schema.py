"""Load and validate JSON sources of truth against bundled JSON Schemas."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any

import jsonschema
from jsonschema import Draft202012Validator

SCHEMA_FILES = {
    "config": "config.schema.json",
    "policy": "policy.schema.json",
    "req-meta": "req-meta.schema.json",
    "contract": "contract.schema.json",
    "gate": "gate.schema.json",
    "gate-runtime": "gate.runtime.schema.json",
    "knowledge": "knowledge.schema.json",
}


def schemas_root() -> Path:
    """Return the on-disk directory containing the bundled schemas."""
    pkg_root = resources.files("qgb").joinpath("schemas")
    # resources.files returns a Traversable; for our editable install it
    # resolves to a real path.
    return Path(str(pkg_root))


def load_schema(name: str) -> dict[str, Any]:
    """Load a schema by short name (e.g. "gate", "policy")."""
    if name not in SCHEMA_FILES:
        raise KeyError(f"Unknown schema name: {name!r}. Known: {sorted(SCHEMA_FILES)}")
    path = schemas_root() / SCHEMA_FILES[name]
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


@dataclass(frozen=True)
class ValidationIssue:
    """A single JSON Schema validation error."""

    path: str          # JSON Pointer-ish path, e.g. "/stages/0/responsibility"
    message: str
    schema_path: str   # Path inside the schema that failed

    @classmethod
    def from_error(cls, err: jsonschema.ValidationError) -> ValidationIssue:
        instance_path = (
            "/" + "/".join(str(p) for p in err.absolute_path)
            if err.absolute_path
            else "/"
        )
        schema_path = (
            "/" + "/".join(str(p) for p in err.absolute_schema_path)
            if err.absolute_schema_path
            else "/"
        )
        return cls(path=instance_path, message=err.message, schema_path=schema_path)


def validate(instance: Mapping[str, Any], schema_name: str) -> list[ValidationIssue]:
    """Validate an instance against the named schema. Returns issues (empty = valid)."""
    schema = load_schema(schema_name)
    validator = Draft202012Validator(schema)
    return [ValidationIssue.from_error(e) for e in validator.iter_errors(instance)]


def is_valid(instance: Mapping[str, Any], schema_name: str) -> bool:
    """Convenience: True iff the instance has zero validation issues."""
    return not validate(instance, schema_name)
