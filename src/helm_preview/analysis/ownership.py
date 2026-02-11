"""Ownership detection (Helm, ArgoCD, Flux)."""

from __future__ import annotations

from dataclasses import dataclass, field

from helm_preview.parser.manifest import Resource


@dataclass
class OwnershipInfo:
    manager: str  # "helm", "argocd", "flux", "unknown"
    release: str | None = None
    app: str | None = None
    warnings: list[str] = field(default_factory=list)


def detect_ownership(resource: Resource) -> OwnershipInfo:
    """Check annotations/labels to determine resource ownership.

    Checks:
    - app.kubernetes.io/managed-by
    - meta.helm.sh/release-name
    - argocd.argoproj.io/managed-by
    - fluxcd.io/sync-checksum / kustomize.toolkit.fluxcd.io/*
    """
    metadata = resource.body.get("metadata", {})
    labels = metadata.get("labels", {})
    annotations = metadata.get("annotations", {})

    managed_by = labels.get("app.kubernetes.io/managed-by", "")

    # Helm detection
    helm_release = annotations.get("meta.helm.sh/release-name")
    if managed_by.lower() == "helm" or helm_release:
        return OwnershipInfo(
            manager="helm",
            release=helm_release or labels.get("app.kubernetes.io/instance"),
        )

    # ArgoCD detection
    argocd_app = annotations.get("argocd.argoproj.io/managed-by")
    if not argocd_app:
        argocd_app = labels.get("argocd.argoproj.io/instance")
    if argocd_app:
        return OwnershipInfo(
            manager="argocd",
            app=argocd_app,
        )

    # Flux detection
    flux_keys = [k for k in annotations if "fluxcd.io" in k or "kustomize.toolkit.fluxcd.io" in k]
    flux_labels = [k for k in labels if "fluxcd.io" in k or "kustomize.toolkit.fluxcd.io" in k]
    if flux_keys or flux_labels:
        return OwnershipInfo(manager="flux")

    return OwnershipInfo(manager="unknown")
