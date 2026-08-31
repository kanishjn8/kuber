from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from agent_layer.trajectory import TrajectoryEvent
from judge_layer.evaluation.metrics import SystemCaseMetrics
from judge_layer.evaluation.system_benchmarks import SystemBenchmark
from judge_layer.simulator import BenchmarkCase
from rules_engine.models import Policy
from rules_engine.rbac.authorization import is_authorized
from rules_engine.rbac.canonicalizer import effective_permission_count
from rules_engine.risk import score_policy


def _event_label(value: Mapping[str, Any]) -> str:
    group = value.get("api_group") or "core"
    resource = value.get("resource", "unknown")
    name = f"/{value['resource_name']}" if value.get("resource_name") else ""
    namespace = value.get("namespace") or "cluster-wide"
    return f"{value.get('verb', '?')} {group}/{resource}{name} [{namespace}]"


class JudgeEvaluationPresenter:
    """Render deterministic judge evidence with the live sandbox's visual language."""

    def __init__(self, *, console: Console | None = None) -> None:
        self.console = console or Console()

    def start(self, case_count: int, benchmark_root: Path) -> None:
        self.console.print()
        self.console.print(
            Panel.fit(
                "[bold]Deterministic least-privilege evaluation[/bold]\n"
                "Benchmark files define behavior. The RBAC simulator proves PASS or FAIL.",
                title="[bold cyan]KUBER JUDGE[/bold cyan]",
                border_style="cyan",
            )
        )
        facts = Table(show_header=False, box=None)
        facts.add_row("Benchmark root", Text(str(benchmark_root)))
        facts.add_row("Cases discovered", str(case_count))
        facts.add_row("Decision authority", "Files + deterministic RBAC simulator")
        facts.add_row("LLM", "Disabled and not required")
        self.console.print(facts)
        self.console.print(
            f"[dim]Discovered {case_count} benchmark cases under "
            f"{escape(str(benchmark_root))}.[/dim]"
        )

    def case_started(self, index: int, total: int, path: Path, case: BenchmarkCase) -> None:
        self.console.rule(f"[bold cyan][{index:02}/{total:02}] {escape(case.name)}[/bold cyan]")
        self.console.print(
            Panel(Text(case.description), title="Purpose", border_style="cyan", padding=(0, 1))
        )

        source_table = Table("Evidence files:", "Path", header_style="bold")
        for label, name in (
            ("Current grant", "initial-rbac.yaml"),
            ("Runtime evidence", "observed-events.json"),
            ("Owner tests", "verification-tests.yaml"),
            ("Reference", "expected-minimum.yaml"),
        ):
            source_table.add_row(label, Text(str(path / name)))
        self.console.print(source_table)

        initial_risk = score_policy(case.initial_policy).score
        metrics = Table("Input", "Value", header_style="bold")
        metrics.add_row(
            "Initial policy", f"{effective_permission_count(case.initial_policy)} permissions"
        )
        metrics.add_row("Initial risk", f"{initial_risk}/100")
        metrics.add_row("Observed calls", str(len(case.observed_events)))
        metrics.add_row("Declared tests", str(len(case.verification_tests)))
        if case.expected_policy is not None:
            metrics.add_row(
                "Reference minimum",
                f"{effective_permission_count(case.expected_policy)} permissions, "
                f"risk {score_policy(case.expected_policy).score}/100",
            )
        self.console.print(metrics)

        observed_table = Table("Observed normalized calls:", header_style="bold blue")
        for event in case.observed_events:
            observed_table.add_row(Text(_event_label(event.to_dict())))
        self.console.print(observed_table)

        verification = Table(
            "Owner-declared verification tests:",
            "Capability",
            "Visibility",
            header_style="bold",
        )
        observed = set(case.observed_events)
        for test in case.verification_tests:
            for event in test.events:
                hidden = event not in observed
                visibility = (
                    Text("HIDDEN PATH", style="bold yellow") if hidden else Text("observed")
                )
                verification.add_row(
                    Text(test.name), Text(_event_label(event.to_dict())), visibility
                )
        self.console.print(verification)

    def baseline(self, case: BenchmarkCase, policy: Policy, metrics: SystemCaseMetrics) -> None:
        self.console.print("[bold yellow]Observed-only baseline:[/bold yellow]")
        comparison = Table("Metric", "Before", "Candidate", header_style="bold yellow")
        comparison.add_row(
            "Effective permissions",
            str(metrics.initial_permissions),
            str(metrics.final_permissions),
        )
        comparison.add_row("Risk score", str(metrics.initial_risk), str(metrics.final_risk))
        self.console.print(comparison)

        tests = Table("Test", "Status", "Deterministic evidence", header_style="bold")
        passed = 0
        for test in case.verification_tests:
            denied = tuple(event for event in test.events if not is_authorized(policy, event))
            if denied:
                status = Text("FAIL", style="bold red")
                evidence = Text(
                    "\n".join(f"DENIED {_event_label(item.to_dict())}" for item in denied)
                )
            else:
                passed += 1
                status = Text("PASS", style="bold green")
                evidence = Text("All declared capabilities authorized", style="green")
            tests.add_row(Text(test.name), status, evidence)
        self.console.print(tests)

        successful = metrics.functional_success
        result = (
            f"{'PASS' if successful else 'FAIL'} ({passed}/{len(case.verification_tests)} tests); "
            f"validated risk reduction {metrics.validated_risk_reduction:.1f}%"
        )
        self.console.print(
            Panel.fit(
                Text(result),
                title="Baseline result",
                border_style="green" if successful else "red",
            )
        )

    def agent_started(self) -> None:
        self.console.print("[bold magenta]Kuber agent flow:[/bold magenta]")

    def system_case_started(self, index: int, total: int, benchmark: SystemBenchmark) -> None:
        self.console.rule(f"[bold cyan][{index:02d}/{total:02d}] {benchmark.name}")
        self.console.print(Panel(benchmark.description, title="Multi-service benchmark"))
        services = Table("Workload", "Declared tests", header_style="bold cyan")
        for case in benchmark.cases:
            services.add_row(case.identifier, str(len(case.verification_tests)))
        self.console.print(services)
        self.console.print(
            f"Dispatching through [bold]{benchmark.workers}[/bold] in-memory consumer workers "
            "using production event contracts and the LangGraph workload subgraph."
        )

    def system_case_finished(self, baseline: SystemCaseMetrics, kuber: SystemCaseMetrics) -> None:
        table = Table("Metric", "Observed-only", "Kuber", header_style="bold green")
        table.add_row(
            "Functional success",
            "PASS" if baseline.functional_success else "FAIL",
            "PASS" if kuber.functional_success else "FAIL",
        )
        table.add_row(
            "Permissions",
            f"{baseline.initial_permissions} → {baseline.final_permissions}",
            f"{kuber.initial_permissions} → {kuber.final_permissions}",
        )
        table.add_row(
            "Validated risk reduction",
            f"{baseline.validated_risk_reduction:.1f}%",
            f"{kuber.validated_risk_reduction:.1f}%",
        )
        table.add_row("Repairs", str(baseline.repair_iterations), str(kuber.repair_iterations))
        table.add_row(
            "Observed wall time",
            f"{baseline.runtime_seconds:.4f}s",
            f"{kuber.runtime_seconds:.4f}s",
        )
        self.console.print(table)

    def handle_event(self, event: TrajectoryEvent) -> None:
        details = event.details
        if event.agent == "inspector" and event.action == "inspect":
            self.console.print(
                Text.assemble(
                    ("  Inspector -> ", "bold blue"),
                    f"resolved {details['permissions']} permissions, risk {details['risk']}/100",
                )
            )
        elif event.agent == "inspector" and event.action == "gather_evidence":
            self.console.print(
                Text.assemble(
                    ("  Evidence  -> ", "bold blue"),
                    f"{len(details['observed_events'])} normalized observed calls",
                )
            )
        elif event.agent == "reducer" and event.action == "propose_policy":
            self.console.print(
                Text.assemble(
                    ("  Reducer   -> ", "bold yellow"),
                    f"proposed {details['permissions']} permissions "
                    f"(removed {details['removed_permissions']}), risk {details['risk']}/100",
                )
            )
            for permission in details["candidate_permissions"]:
                self.console.print(Text(f"      GRANT {permission}", style="yellow"))
        elif event.agent == "verifier" and event.action == "apply_policy":
            self.console.print(
                Text.assemble(
                    ("  Verifier  -> ", "bold magenta"),
                    f"attempt {details['attempt']}: apply {details['permissions']} permissions",
                )
            )
        elif event.agent == "verifier" and event.action == "verify":
            passed = event.decision == "accept"
            status = "PASS" if passed else "FAIL"
            self.console.print(
                Text.assemble(
                    ("  Verifier  -> ", "bold magenta"),
                    (status, "bold green" if passed else "bold red"),
                    f" {details['tests_passed']}/{details['tests_total']} declared tests",
                )
            )
            for value in details.get("denied_events", []):
                self.console.print(Text(f"      DENIED {_event_label(value)}", style="bold red"))
        elif event.agent == "verifier" and event.action == "repair_policy":
            restored = "\n".join(f"RESTORE {_event_label(value)}" for value in details["restored"])
            self.console.print(
                Panel(
                    Text(restored, style="magenta"),
                    title="Repair -> restore only originally authorized denied capabilities",
                    border_style="magenta",
                    padding=(0, 1),
                )
            )
        elif event.agent == "orchestrator" and event.action == "finalize":
            self.console.print(
                Panel.fit(
                    f"[bold green]ACCEPT[/bold green] {details['permissions']} permissions, "
                    f"risk {details['risk']}/100",
                    title="Finalize",
                    border_style="green",
                )
            )
        elif event.agent == "orchestrator" and event.action == "restore_policy":
            self.console.print(
                Panel.fit(
                    "[bold red]REJECT[/bold red] candidate and restore original policy",
                    title="Finalize",
                    border_style="red",
                )
            )

    def case_finished(
        self,
        metrics: SystemCaseMetrics,
        final_policy: Policy,
        trajectory_path: Path,
    ) -> None:
        self.console.print("[bold green]Case outcome:[/bold green]")
        outcome = Table("Metric", "Before", "After", header_style="bold green")
        outcome.add_row(
            "Effective permissions",
            str(metrics.initial_permissions),
            str(metrics.final_permissions),
        )
        outcome.add_row("Risk score", str(metrics.initial_risk), str(metrics.final_risk))
        outcome.add_row(
            "Verification", "not proven", "PASS" if metrics.functional_success else "FAIL"
        )
        outcome.add_row("Validated risk reduction", "—", f"{metrics.validated_risk_reduction:.1f}%")
        outcome.add_row("Repair iterations", "—", str(metrics.repair_iterations))
        self.console.print(outcome)

        grants = Table(
            f"Final grants ({len(final_policy.permissions)} normalized rules):",
            header_style="bold",
        )
        for permission in final_policy.permissions:
            grants.add_row(Text(permission.display()))
        self.console.print(grants)
        self.console.print(f"Machine trajectory: [cyan]{escape(str(trajectory_path))}[/cyan]")

    def finish(self, summary: str, artifact_root: Path) -> None:
        self.console.rule("[bold green]Aggregate evaluation")
        self.console.print(Panel(Text(summary), border_style="green"))
        artifacts = Table(show_header=False, box=None)
        artifacts.add_row("Generated evidence:", Text(str(artifact_root / "results.json")))
        artifacts.add_row("Generated comparison:", Text(str(artifact_root / "report.md")))
        self.console.print(artifacts)
