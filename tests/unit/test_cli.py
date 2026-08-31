from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from kuber_cli import cli
from kuber_cli.cli import app
from rules_engine.models import ServiceAccountRef
from rules_engine.rbac import parse_rbac, resolve_effective_policy
from rules_engine.risk import score_policy

runner = CliRunner()


def test_inspect_command_reports_effective_policy() -> None:
    manifest = "judge_layer/benchmarks/01_config_reader/initial-rbac.yaml"
    result = runner.invoke(
        app,
        [
            "inspect",
            manifest,
            "config-reader",
            "payments",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Effective permissions: 49" in result.output
    policy = resolve_effective_policy(
        parse_rbac(Path(manifest)), ServiceAccountRef("config-reader", "payments")
    )
    assert f"Privilege risk score: {score_policy(policy).score}/100" in result.output


def test_minimize_command_writes_round_trippable_candidate(tmp_path: Path) -> None:
    events = tmp_path / "events.json"
    output = tmp_path / "candidate.yaml"
    events.write_text(
        json.dumps(
            [
                {
                    "api_group": "",
                    "resource": "configmaps",
                    "verb": "get",
                    "namespace": "payments",
                    "resource_name": "app-config",
                }
            ]
        ),
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        [
            "minimize",
            "judge_layer/benchmarks/01_config_reader/initial-rbac.yaml",
            str(events),
            "config-reader",
            "payments",
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 0, result.output
    candidate = resolve_effective_policy(
        parse_rbac(output), ServiceAccountRef("config-reader", "payments")
    )
    assert len(candidate.permissions) == 1
    assert candidate.permissions[0].resource_name == "app-config"
    assert "Unverified candidate written" in result.output


def test_report_command_handles_missing_and_existing_reports(tmp_path: Path) -> None:
    missing = runner.invoke(app, ["report", "--path", str(tmp_path / "missing.md")])
    assert missing.exit_code != 0
    assert "report not found" in missing.output

    report = tmp_path / "report.md"
    report.write_text("# Generated evidence\n", encoding="utf-8")
    present = runner.invoke(app, ["report", "--path", str(report)])
    assert present.exit_code == 0
    assert "Generated evidence" in present.output


def test_help_lists_supported_workflows() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0, result.output
    for command in (
        "discover",
        "inspect",
        "minimize",
        "evaluate",
        "report",
        "trajectory",
        "experiment-context",
        "experiment-workers",
        "optimize",
    ):
        assert command in result.output


def test_discover_persists_and_prints_opted_in_services(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    service = SimpleNamespace(
        service_id="payment-service",
        deployment_name="payment-service",
        service_account="payment-service-sa",
        source_repository=SimpleNamespace(local_path="examples/service_catalog/payment_service"),
    )

    class Discovery:
        def __init__(self, **kwargs: object) -> None:
            assert kwargs["context"] == "kind-kuber"

        def discover(self, namespace: str) -> tuple[object, ...]:
            assert namespace == "kuber-sandbox"
            return (service,)

    stored: list[object] = []

    class Registry:
        def __init__(self, path: Path) -> None:
            assert path == tmp_path / "services.sqlite"

        def put(self, value: object) -> None:
            stored.append(value)

        def close(self) -> None:
            stored.append("closed")

    monkeypatch.setattr(cli, "KubernetesServiceDiscovery", Discovery)
    monkeypatch.setattr(cli, "SQLiteServiceRegistry", Registry)
    result = runner.invoke(
        app,
        ["discover", "--database", str(tmp_path / "services.sqlite")],
    )

    assert result.exit_code == 0, result.output
    assert "ServiceAccount/payment-service-sa" in result.output
    assert stored == [service, "closed"]


def test_trajectory_lists_scoped_and_legacy_files(tmp_path: Path) -> None:
    scoped = tmp_path / "run-1"
    scoped.mkdir()
    (scoped / "service.jsonl").write_text("{}\n", encoding="utf-8")
    result = runner.invoke(app, ["trajectory", "run-1", "--root", str(tmp_path)])
    missing = runner.invoke(app, ["trajectory", "missing", "--root", str(tmp_path)])

    assert result.exit_code == 0
    assert "service.jsonl" in result.output
    assert missing.exit_code != 0
    assert "trajectory not found" in missing.output


def test_evaluate_command_delegates_to_deterministic_runner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[bool] = []
    monkeypatch.setattr(cli, "run_evaluation", lambda *, detailed: calls.append(detailed))

    result = runner.invoke(app, ["evaluate"])

    assert result.exit_code == 0, result.output
    assert calls == [True]


def test_evaluate_command_supports_summary_only(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[bool] = []
    monkeypatch.setattr(cli, "run_evaluation", lambda *, detailed: calls.append(detailed))

    result = runner.invoke(app, ["evaluate", "--summary-only"])

    assert result.exit_code == 0, result.output
    assert calls == [False]


def test_optimize_command_refuses_unrecognized_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        cli,
        "KubernetesEnvironment",
        lambda: SimpleNamespace(dry_run=True),
    )

    result = runner.invoke(app, ["optimize"])

    assert result.exit_code == 1
    assert "kind-kuber with the sandbox namespace label is required" in result.output
