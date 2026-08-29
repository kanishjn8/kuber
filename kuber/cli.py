from __future__ import annotations

import json
import subprocess
from pathlib import Path

import typer

from agent_layer.llm import FailureReasoner, provider_from_environment
from agent_layer.orchestrator import KuberOrchestrator
from demo_layer.adapter import KubernetesEnvironment, SafetyError
from judge_layer.evaluation.runner import run_evaluation
from rules_engine.minimizer import observed_only_policy
from rules_engine.models import KubeEvent, ServiceAccountRef
from rules_engine.rbac import parse_rbac, policy_to_yaml, resolve_effective_policy
from rules_engine.rbac.canonicalizer import effective_permission_count
from rules_engine.risk import score_policy

app = typer.Typer(help="Kuber: verified least-privilege compilation for Kubernetes workloads.")


@app.command()
def inspect(manifest: Path, service_account: str, namespace: str) -> None:
    """Resolve and summarize one ServiceAccount's supported effective RBAC."""

    policy = resolve_effective_policy(parse_rbac(manifest), ServiceAccountRef(service_account, namespace))
    risk = score_policy(policy)
    typer.echo(f"Effective permissions: {effective_permission_count(policy)}")
    typer.echo(f"Privilege risk score: {risk.score}/100")
    for finding in risk.findings:
        typer.echo(f"+ {finding.reason}: {finding.points} ({finding.occurrences} occurrence(s))")


@app.command()
def minimize(manifest: Path, events: Path, service_account: str, namespace: str, output: Path = Path("artifacts/policies/candidate.yaml")) -> None:
    """Generate an observed-only candidate; it is not accepted without verification."""

    current = resolve_effective_policy(parse_rbac(manifest), ServiceAccountRef(service_account, namespace))
    values = json.loads(events.read_text(encoding="utf-8"))
    observed = tuple(KubeEvent.from_dict(value) for value in values)
    candidate = observed_only_policy(current, observed)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(policy_to_yaml(candidate), encoding="utf-8")
    typer.echo(f"Unverified candidate written to {output}")


@app.command()
def evaluate() -> None:
    """Run the Kubernetes-free benchmark suite and write generated artifacts."""

    run_evaluation()


@app.command()
def report(path: Path = Path("artifacts/evaluation/report.md")) -> None:
    """Print the latest generated evaluation report."""

    if not path.exists():
        raise typer.BadParameter("report not found; run `kuber evaluate` first")
    typer.echo(path.read_text(encoding="utf-8"))


@app.command()
def demo() -> None:
    """Run warmup and Kuber against the guarded kind-kuber sandbox."""

    try:
        environment = KubernetesEnvironment()
        if environment.dry_run:
            raise SafetyError("kind-kuber with the sandbox namespace label is required")
        subprocess.run(("./demo_layer/scripts/warmup.sh",), check=True)
        orchestrator = KuberOrchestrator(failure_reasoner=FailureReasoner(provider_from_environment()))
        result = orchestrator.run(environment, run_id="kind-payment-controller")
    except (SafetyError, FileNotFoundError, subprocess.SubprocessError) as exc:
        typer.echo(f"Demo unavailable: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(f"Verification: {result.verification.tests_passed}/{result.verification.tests_total}")
    typer.echo(f"Risk: {result.original_risk.score} -> {result.final_risk.score}")
    typer.echo(f"Repairs: {result.repair_iterations}")


if __name__ == "__main__":
    app()

