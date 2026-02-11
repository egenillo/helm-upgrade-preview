"""Shell out to kubectl CLI."""

from __future__ import annotations

from helm_preview.core.runner import run


def _kube_flags(**kube_opts: str | None) -> list[str]:
    """Build common kubectl flags from options."""
    flags: list[str] = []
    if kube_opts.get("kubeconfig"):
        flags += ["--kubeconfig", kube_opts["kubeconfig"]]
    if kube_opts.get("kube_context"):
        flags += ["--context", kube_opts["kube_context"]]
    return flags


def server_side_dry_run(
    manifest_yaml: str, namespace: str, **kube_opts: str | None
) -> str:
    """kubectl apply --dry-run=server -o yaml -f - -> post-mutation YAML.

    Feeds single-resource YAML via stdin.
    """
    cmd = [
        "kubectl", "apply",
        "--dry-run=server",
        "-o", "yaml",
        "-n", namespace,
        "-f", "-",
    ]
    cmd += _kube_flags(**kube_opts)
    return run(cmd, stdin=manifest_yaml)
