"""Semantic comparison utilities for YAML resource bodies."""

from __future__ import annotations


def is_semantically_equal(old: dict, new: dict) -> bool:
    """After normalization, check if two resource bodies are semantically equivalent.

    Handles:
    - Numeric string vs int (e.g. port "80" vs 80)
    - Boolean string vs bool (e.g. "true" vs True)
    - null vs missing key
    """
    return _deep_semantic_equal(old, new)


def _deep_semantic_equal(a: object, b: object) -> bool:
    """Recursively compare two values with semantic coercion."""
    # Direct equality
    if a == b:
        return True

    # None vs missing: treat None as equal to absent
    if a is None and b is None:
        return True

    # Numeric coercion: "80" == 80
    if _coerce_numeric(a) is not None and _coerce_numeric(b) is not None:
        return _coerce_numeric(a) == _coerce_numeric(b)

    # Boolean coercion: "true" == True
    if _coerce_bool(a) is not None and _coerce_bool(b) is not None:
        return _coerce_bool(a) == _coerce_bool(b)

    # Dict comparison
    if isinstance(a, dict) and isinstance(b, dict):
        all_keys = set(a.keys()) | set(b.keys())
        for key in all_keys:
            val_a = a.get(key)
            val_b = b.get(key)
            # Treat missing key as None
            if not _deep_semantic_equal(val_a, val_b):
                return False
        return True

    # List comparison
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            return False
        return all(_deep_semantic_equal(x, y) for x, y in zip(a, b))

    return False


def _coerce_numeric(val: object) -> int | float | None:
    """Try to coerce a value to a number."""
    if isinstance(val, (int, float)) and not isinstance(val, bool):
        return val
    if isinstance(val, str):
        try:
            return int(val)
        except ValueError:
            try:
                return float(val)
            except ValueError:
                return None
    return None


_BOOL_MAP = {
    "true": True,
    "false": False,
    "yes": True,
    "no": False,
}


def _coerce_bool(val: object) -> bool | None:
    """Try to coerce a value to a boolean."""
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return _BOOL_MAP.get(val.lower())
    return None
