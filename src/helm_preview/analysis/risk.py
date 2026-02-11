"""Risk detection rules engine."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable

from helm_preview.config import IMMUTABLE_FIELDS
from helm_preview.diff.engine import ChangeRecord


class RiskLevel(Enum):
    SAFE = "safe"
    WARNING = "warning"
    DANGER = "danger"


@dataclass
class RiskAnnotation:
    level: RiskLevel
    rule: str
    message: str
    path: str


def check_immutable_fields(change: ChangeRecord) -> list[RiskAnnotation]:
    """Detects changes to known immutable fields."""
    annotations: list[RiskAnnotation] = []
    kind_lower = change.kind.lower()
    immutable_paths = IMMUTABLE_FIELDS.get(kind_lower, [])

    for fc in change.changes:
        for imm_path in immutable_paths:
            if fc.path.startswith(imm_path):
                annotations.append(RiskAnnotation(
                    level=RiskLevel.DANGER,
                    rule="immutable_field",
                    message=f"Immutable field '{fc.path}' changed on {change.kind}/{change.name}",
                    path=fc.path,
                ))
    return annotations


def check_service_type_change(change: ChangeRecord) -> list[RiskAnnotation]:
    """Service type changes (especially ClusterIP -> NodePort/LoadBalancer)."""
    if change.kind != "Service":
        return []

    annotations: list[RiskAnnotation] = []
    for fc in change.changes:
        if fc.path == "spec.type":
            level = RiskLevel.WARNING
            if fc.old_value == "ClusterIP" and fc.new_value in ("NodePort", "LoadBalancer"):
                level = RiskLevel.DANGER
            annotations.append(RiskAnnotation(
                level=level,
                rule="service_type_change",
                message=f"Service type changed from {fc.old_value} to {fc.new_value}",
                path=fc.path,
            ))
    return annotations


def check_pvc_changes(change: ChangeRecord) -> list[RiskAnnotation]:
    """PVC storage size or storageClass changes."""
    if change.kind != "PersistentVolumeClaim":
        return []

    annotations: list[RiskAnnotation] = []
    for fc in change.changes:
        if "storage" in fc.path and "requests" in fc.path:
            annotations.append(RiskAnnotation(
                level=RiskLevel.WARNING,
                rule="pvc_storage_change",
                message=f"PVC storage request changed from {fc.old_value} to {fc.new_value}",
                path=fc.path,
            ))
        if fc.path == "spec.storageClassName":
            annotations.append(RiskAnnotation(
                level=RiskLevel.DANGER,
                rule="pvc_storage_class_change",
                message=f"PVC storageClassName changed from {fc.old_value} to {fc.new_value}",
                path=fc.path,
            ))
    return annotations


def check_resource_deletion(change: ChangeRecord) -> list[RiskAnnotation]:
    """Any removed resource gets at least WARNING."""
    if change.status != "removed":
        return []
    return [RiskAnnotation(
        level=RiskLevel.WARNING,
        rule="resource_deleted",
        message=f"{change.kind}/{change.name} will be removed",
        path="",
    )]


def check_crd_changes(change: ChangeRecord) -> list[RiskAnnotation]:
    """CRD spec changes (schema, scope, versions) -> DANGER."""
    if change.kind != "CustomResourceDefinition":
        return []

    annotations: list[RiskAnnotation] = []
    danger_prefixes = ("spec.scope", "spec.versions", "spec.validation", "spec.names")
    for fc in change.changes:
        for prefix in danger_prefixes:
            if fc.path.startswith(prefix):
                annotations.append(RiskAnnotation(
                    level=RiskLevel.DANGER,
                    rule="crd_spec_change",
                    message=f"CRD spec change at '{fc.path}' on {change.name}",
                    path=fc.path,
                ))
                break
    return annotations


def check_rbac_escalation(change: ChangeRecord) -> list[RiskAnnotation]:
    """ClusterRole/Role rule changes -> WARNING."""
    if change.kind not in ("ClusterRole", "Role"):
        return []

    annotations: list[RiskAnnotation] = []
    for fc in change.changes:
        if fc.path.startswith("rules"):
            annotations.append(RiskAnnotation(
                level=RiskLevel.WARNING,
                rule="rbac_change",
                message=f"RBAC rules changed at '{fc.path}' on {change.kind}/{change.name}",
                path=fc.path,
            ))
    return annotations


# Rules registry
RISK_RULES: list[Callable[[ChangeRecord], list[RiskAnnotation]]] = [
    check_immutable_fields,
    check_service_type_change,
    check_pvc_changes,
    check_resource_deletion,
    check_crd_changes,
    check_rbac_escalation,
]


def assess_risk(
    changes: list[ChangeRecord],
) -> list[tuple[ChangeRecord, list[RiskAnnotation]]]:
    """Run all rules against all changes. Attach annotations."""
    results: list[tuple[ChangeRecord, list[RiskAnnotation]]] = []
    for change in changes:
        annotations: list[RiskAnnotation] = []
        for rule in RISK_RULES:
            annotations.extend(rule(change))
        results.append((change, annotations))
    return results
