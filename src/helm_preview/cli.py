"""Click CLI entry point for helm-preview."""

from __future__ import annotations

import sys

import click
import yaml

from helm_preview.analysis.ownership import OwnershipInfo, detect_ownership
from helm_preview.analysis.risk import RiskAnnotation, assess_risk
from helm_preview.core.helm import dry_run_upgrade, get_manifest
from helm_preview.core.kubectl import server_side_dry_run
from helm_preview.core.runner import RunError
from helm_preview.diff.engine import ChangeRecord, diff_all
from helm_preview.output.json_out import render_json
from helm_preview.output.terminal import render_terminal
from helm_preview.parser.manifest import (
    Resource,
    parse_multi_doc,
    pair_resources,
)


@click.group()
@click.version_option()
def main() -> None:
    """helm-preview: Semantic, noise-filtered, risk-aware diffs for Helm upgrades."""


@main.command()
@click.argument("release")
@click.argument("chart")
@click.option("-n", "--namespace", default=None, help="Kubernetes namespace")
@click.option("-f", "--values", multiple=True, help="Values file(s)")
@click.option("--set", "set_values", multiple=True, help="Set values (key=val)")
@click.option("--version", default=None, help="Chart version")
@click.option("--server-side", is_flag=True, help="Truth-diff via server-side dry-run")
@click.option("--show-all", is_flag=True, help="Disable noise filtering")
@click.option(
    "-o", "--output", "output_format",
    type=click.Choice(["terminal", "json"]),
    default="terminal",
    help="Output format",
)
@click.option("--context", default=3, type=int, help="Lines of context around changes")
@click.option("--ignore-path", multiple=True, help="Additional dot-paths to ignore")
@click.option("--kubeconfig", default=None, help="Path to kubeconfig")
@click.option("--kube-context", default=None, help="Kubernetes context to use")
@click.option("--no-color", is_flag=True, help="Disable colored output")
@click.option("--risk-only", is_flag=True, help="Only show WARNING/DANGER changes")
def diff(
    release: str,
    chart: str,
    namespace: str | None,
    values: tuple[str, ...],
    set_values: tuple[str, ...],
    version: str | None,
    server_side: bool,
    show_all: bool,
    output_format: str,
    context: int,
    ignore_path: tuple[str, ...],
    kubeconfig: str | None,
    kube_context: str | None,
    no_color: bool,
    risk_only: bool,
) -> None:
    """Preview the diff of a Helm upgrade."""
    ns = namespace or "default"
    kube_opts = {
        "kubeconfig": kubeconfig,
        "kube_context": kube_context,
    }

    try:
        # 1. Fetch live manifests
        live_yaml = get_manifest(release, ns, **kube_opts)
        live_resources = parse_multi_doc(live_yaml, default_namespace=ns)

        # 2. Render upgrade (dry-run)
        upgrade_yaml = dry_run_upgrade(
            release, chart, ns,
            values_files=list(values),
            set_values=list(set_values),
            version=version,
            **kube_opts,
        )
        upgrade_resources = parse_multi_doc(upgrade_yaml, default_namespace=ns)

        # 3. Optional: server-side dry-run
        if server_side:
            upgrade_resources = _apply_server_side(upgrade_resources, ns, **kube_opts)

        # 4. Parse & pair
        pairs = pair_resources(live_resources, upgrade_resources)

        # 5-6. Filter, normalize & diff
        change_records = diff_all(
            pairs,
            show_all=show_all,
            extra_ignores=list(ignore_path) if ignore_path else None,
        )

        # 7. Risk analysis + ownership
        risk_results = assess_risk(change_records)
        full_results: list[tuple[ChangeRecord, list[RiskAnnotation], OwnershipInfo | None]] = []
        for change, risk_annotations in risk_results:
            # Detect ownership from the new resource (or old if removed)
            resource = _find_resource(change, live_resources, upgrade_resources)
            ownership = detect_ownership(resource) if resource else None
            full_results.append((change, risk_annotations, ownership))

        # Count unchanged for JSON output
        total_unchanged = sum(1 for p in pairs if p.status == "unchanged")

        # 8. Output
        if output_format == "json":
            click.echo(render_json(full_results, total_unchanged=total_unchanged))
        else:
            render_terminal(
                full_results,
                context_lines=context,
                show_all=show_all,
                no_color=no_color,
                risk_only=risk_only,
            )

    except RunError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


def _apply_server_side(
    resources: list[Resource], namespace: str, **kube_opts: str | None
) -> list[Resource]:
    """Apply server-side dry-run to each resource for truth-diff mode."""
    results: list[Resource] = []
    for res in resources:
        try:
            mutated_yaml = server_side_dry_run(
                yaml.dump(res.body), namespace, **kube_opts
            )
            mutated = parse_multi_doc(mutated_yaml, default_namespace=namespace)
            if mutated:
                results.append(mutated[0])
            else:
                results.append(res)
        except RunError:
            # If server-side dry-run fails for a resource, use the original
            results.append(res)
    return results


def _find_resource(
    change: ChangeRecord,
    old_resources: list[Resource],
    new_resources: list[Resource],
) -> Resource | None:
    """Find the Resource object for a change record."""
    # Prefer new resource, fall back to old
    for res in new_resources:
        if res.key == change.resource_key:
            return res
    for res in old_resources:
        if res.key == change.resource_key:
            return res
    return None
