"""Structural YAML diff engine using deepdiff."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from deepdiff import DeepDiff

from helm_preview.diff.filters import normalize_body, strip_noise
from helm_preview.diff.semantic import is_semantically_equal
from helm_preview.parser.manifest import ResourcePair


@dataclass
class FieldChange:
    path: str
    old_value: Any
    new_value: Any
    change_type: str  # "value_changed", "item_added", "item_removed", "type_changed"


@dataclass
class ChangeRecord:
    resource_key: str
    kind: str
    name: str
    namespace: str
    status: Literal["added", "removed", "changed"]
    changes: list[FieldChange] = field(default_factory=list)


def compute_diff(
    pair: ResourcePair,
    show_all: bool = False,
    extra_ignores: list[str] | None = None,
) -> ChangeRecord | None:
    """Compute diff for a single resource pair.

    Returns None for unchanged resources.
    """
    if pair.status == "unchanged":
        return None

    if pair.status == "added":
        res = pair.new
        assert res is not None
        return ChangeRecord(
            resource_key=res.key,
            kind=res.kind,
            name=res.name,
            namespace=res.namespace,
            status="added",
        )

    if pair.status == "removed":
        res = pair.old
        assert res is not None
        return ChangeRecord(
            resource_key=res.key,
            kind=res.kind,
            name=res.name,
            namespace=res.namespace,
            status="removed",
        )

    # status == "changed"
    assert pair.old is not None and pair.new is not None
    old_body = pair.old.body
    new_body = pair.new.body

    if not show_all:
        old_body = strip_noise(old_body, extra_ignores)
        new_body = strip_noise(new_body, extra_ignores)

    old_body = normalize_body(old_body)
    new_body = normalize_body(new_body)

    # Check semantic equality after normalization
    if is_semantically_equal(old_body, new_body):
        return None

    dd = DeepDiff(old_body, new_body, verbose_level=2)

    changes = _extract_changes(dd)

    if not changes:
        return None

    return ChangeRecord(
        resource_key=pair.old.key,
        kind=pair.old.kind,
        name=pair.old.name,
        namespace=pair.old.namespace,
        status="changed",
        changes=changes,
    )


def _extract_changes(dd: DeepDiff) -> list[FieldChange]:
    """Convert DeepDiff output to FieldChange list."""
    changes: list[FieldChange] = []

    for path, detail in dd.get("values_changed", {}).items():
        changes.append(FieldChange(
            path=_deepdiff_path_to_dot(path),
            old_value=detail.get("old_value"),
            new_value=detail.get("new_value"),
            change_type="value_changed",
        ))

    for path, detail in dd.get("type_changes", {}).items():
        changes.append(FieldChange(
            path=_deepdiff_path_to_dot(path),
            old_value=detail.get("old_value"),
            new_value=detail.get("new_value"),
            change_type="type_changed",
        ))

    for path, value in dd.get("dictionary_item_added", {}).items():
        changes.append(FieldChange(
            path=_deepdiff_path_to_dot(path),
            old_value=None,
            new_value=value,
            change_type="item_added",
        ))

    for path, value in dd.get("dictionary_item_removed", {}).items():
        changes.append(FieldChange(
            path=_deepdiff_path_to_dot(path),
            old_value=value,
            new_value=None,
            change_type="item_removed",
        ))

    for path, value in dd.get("iterable_item_added", {}).items():
        changes.append(FieldChange(
            path=_deepdiff_path_to_dot(path),
            old_value=None,
            new_value=value,
            change_type="item_added",
        ))

    for path, value in dd.get("iterable_item_removed", {}).items():
        changes.append(FieldChange(
            path=_deepdiff_path_to_dot(path),
            old_value=value,
            new_value=None,
            change_type="item_removed",
        ))

    return changes


def _deepdiff_path_to_dot(path: str) -> str:
    """Convert DeepDiff path like root['spec']['replicas'] to spec.replicas."""
    # Remove root prefix
    path = path.replace("root", "", 1)
    # Convert ['key'] to .key and [0] to [0]
    result = ""
    i = 0
    while i < len(path):
        if path[i] == "[":
            end = path.index("]", i)
            inner = path[i + 1 : end]
            if inner.startswith("'") or inner.startswith('"'):
                # Dict key
                key = inner.strip("'\"")
                if result:
                    result += "."
                result += key
            else:
                # List index
                result += f"[{inner}]"
            i = end + 1
        else:
            i += 1
    return result


def diff_all(
    pairs: list[ResourcePair],
    show_all: bool = False,
    extra_ignores: list[str] | None = None,
) -> list[ChangeRecord]:
    """Compute diff for all pairs, filter out unchanged."""
    results: list[ChangeRecord] = []
    for pair in pairs:
        record = compute_diff(pair, show_all=show_all, extra_ignores=extra_ignores)
        if record is not None:
            results.append(record)
    return results
