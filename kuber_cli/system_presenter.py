from __future__ import annotations

from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from agent_layer.graphs import SystemRunResult
from agent_layer.trajectory import TrajectoryEvent


class SystemPresenter:
    """Readable live view of concurrent event and graph execution."""

    def __init__(self, console: Console | None = None, *, llm_label: str) -> None:
        self.console = console or Console()
        self.llm_label = llm_label

    def start(self) -> None:
        self.console.print(
            Panel.fit(
                "[bold]Kuber multi-service least-privilege compiler[/bold]\n"
                "Kubernetes discovery → scoped contexts → Kafka tasks → worker LangGraphs → system E2E\n"
                f"LLM reasoning: {self.llm_label}",
                border_style="cyan",
            )
        )

    def preparation(self, output: str) -> None:
        self.console.print("[green]✓ Starting policies and workloads reset[/green]")
        for line in output.splitlines():
            if line.startswith("KUBER_WARMUP") or line.startswith("Warmup complete"):
                self.console.print(f"  {line}")

    def graph_event(self, event: TrajectoryEvent) -> None:
        service = event.environment.removeprefix("kubernetes:kind-kuber/kuber-sandbox:")
        prefix = f"[cyan]{service}[/cyan] [bold]{event.action.upper()}[/bold]"
        if event.action == "verify":
            color = "green" if event.decision == "accept" else "red"
            self.console.print(f"{prefix} [{color}]{event.reason}[/{color}]")
            for denied in event.details.get("denied_events", []):
                group = denied.get("api_group") or "core"
                self.console.print(
                    Text(
                        f"    REAL 403: {denied['verb']} {group}/{denied['resource']}"
                        f"/{denied.get('resource_name') or '*'}",
                        style="bold red",
                    )
                )
        elif event.action == "diagnose_failure":
            source = event.details.get("reasoner", "deterministic")
            self.console.print(f"{prefix} ({source}) — {event.reason}")
        elif event.action == "repair_policy":
            self.console.print(f"{prefix} — minimum denied capability restored")
        elif event.action in {
            "load_service_context",
            "inspect",
            "gather_evidence",
            "propose_policy",
            "validate_candidate",
            "apply_policy",
            "finalize",
            "publish_result_event",
        }:
            self.console.print(f"{prefix} — {event.reason}")

    def system_event(self, event: TrajectoryEvent) -> None:
        self.console.print(
            f"[magenta]SYSTEM[/magenta] [bold]{event.action.upper()}[/bold] — {event.reason}"
        )

    def finish(self, result: SystemRunResult) -> None:
        table = Table("Service", "Worker", "Permissions", "Risk", "Tests", "Repairs")
        for event in sorted(result.results, key=lambda item: str(item.payload["workload_id"])):
            value = event.payload
            table.add_row(
                str(value["workload_id"]),
                str(value["worker_id"]),
                f"{value['original_permissions']} → {value['final_permissions']}",
                f"{value['original_risk']} → {value['final_risk']}",
                f"{value['tests_passed']}/{value['tests_total']}",
                str(value["repairs"]),
            )
        self.console.print(table)
        status = "PASS" if result.system_passed else "FAIL"
        color = "green" if result.system_passed else "red"
        self.console.print(
            Panel.fit(
                f"[{color}][bold]{status}[/bold][/{color}] — all workload tests and system E2E",
                title="Final system verification",
                border_style=color,
            )
        )
        self.console.print(
            f"Trajectories: [cyan]{Path('artifacts/trajectories') / result.run_id}[/cyan]"
        )
        if result.report_path is not None:
            self.console.print(f"Namespace report: [cyan]{result.report_path}[/cyan]")
