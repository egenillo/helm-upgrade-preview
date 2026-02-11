"""Multi-doc YAML parsing, resource keying, and pairing."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import yaml


@dataclass
class Resource:
    api_version: str
    kind: str
    namespace: str
    name: str
    body: dict
    raw: str

    @property
    def key(self) -> str:
        return f"{self.api_version}/{self.kind}/{self.namespace}/{self.name}"


@dataclass
class ResourcePair:
    old: Resource | None
    new: Resource | None
    status: Literal["added", "removed", "changed", "unchanged"]


def parse_multi_doc(yaml_text: str, default_namespace: str = "default") -> list[Resource]:
    """Split multi-doc YAML (---) into Resource objects.

    Skips empty docs and non-resource docs (those without apiVersion/kind).
    """
    resources: list[Resource] = []
    # Split on --- lines preserving each document's raw text
    raw_docs = _split_raw_docs(yaml_text)

    for raw_doc in raw_docs:
        stripped = raw_doc.strip()
        if not stripped:
            continue

        try:
            body = yaml.safe_load(stripped)
        except yaml.YAMLError:
            continue

        if not isinstance(body, dict):
            continue

        # Skip non-resource docs (must have apiVersion and kind)
        if "apiVersion" not in body or "kind" not in body:
            continue

        metadata = body.get("metadata", {})
        resources.append(Resource(
            api_version=body["apiVersion"],
            kind=body["kind"],
            namespace=metadata.get("namespace", default_namespace),
            name=metadata.get("name", ""),
            body=body,
            raw=stripped,
        ))

    return resources


def _split_raw_docs(yaml_text: str) -> list[str]:
    """Split multi-doc YAML by --- delimiters, returning raw text per doc."""
    docs: list[str] = []
    current_lines: list[str] = []

    for line in yaml_text.splitlines(keepends=True):
        if line.rstrip() == "---":
            if current_lines:
                docs.append("".join(current_lines))
                current_lines = []
        else:
            current_lines.append(line)

    if current_lines:
        docs.append("".join(current_lines))

    return docs


def pair_resources(
    old: list[Resource], new: list[Resource]
) -> list[ResourcePair]:
    """Match resources by key. Returns list of ResourcePair.

    old=None -> ADDED, new=None -> REMOVED, both -> CHANGED/UNCHANGED.
    """
    old_map = {r.key: r for r in old}
    new_map = {r.key: r for r in new}

    all_keys = list(dict.fromkeys(list(old_map.keys()) + list(new_map.keys())))

    pairs: list[ResourcePair] = []
    for key in all_keys:
        old_res = old_map.get(key)
        new_res = new_map.get(key)

        if old_res is None:
            status: Literal["added", "removed", "changed", "unchanged"] = "added"
        elif new_res is None:
            status = "removed"
        elif old_res.body == new_res.body:
            status = "unchanged"
        else:
            status = "changed"

        pairs.append(ResourcePair(old=old_res, new=new_res, status=status))

    return pairs
