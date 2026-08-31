import subprocess
from pathlib import Path
from typing import Any

import pytest

from agent_layer.interfaces import VerificationResult
from kubernetes_runtime.adapter.kubernetes_environment import (
    DryRunOnlyError,
    KubernetesEnvironment,
    SafetyError,
)
from rules_engine.models import KubeEvent, Permission, Policy


def _live_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> KubernetesEnvironment:
    monkeypatch.setattr(KubernetesEnvironment, "_is_recognized_sandbox", lambda self: True)
    return KubernetesEnvironment(dry_run=False, artifact_directory=tmp_path)


def test_unrecognized_environment_defaults_to_dry_run(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(KubernetesEnvironment, "_is_recognized_sandbox", lambda self: False)
    environment = KubernetesEnvironment(artifact_directory=tmp_path)
    assert environment.dry_run
    candidate = Policy(
        (Permission("", "pods", "list", "kuber-sandbox"),),
        name="candidate",
        service_account="payment-service-sa",
        service_account_namespace="kuber-sandbox",
    )
    with pytest.raises(DryRunOnlyError):
        environment.apply_policy(candidate)
    assert (tmp_path / "payment-service-sa.yaml").exists()


def test_unrecognized_environment_refuses_forced_live_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(KubernetesEnvironment, "_is_recognized_sandbox", lambda self: False)

    with pytest.raises(SafetyError, match="live mutation refused"):
        KubernetesEnvironment(dry_run=False)


def test_recognized_environment_reports_live_name_and_policy(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    environment = _live_environment(monkeypatch, tmp_path)

    assert environment.name == "kubernetes:kind-kuber/kuber-sandbox:payment-service:live"
    assert environment.get_current_policy() == environment._original_policy


@pytest.mark.parametrize(
    ("current_context", "namespace_label", "expected"),
    [
        ("kind-kuber", "true", True),
        ("kind-kuber", "false", False),
        ("production", "true", False),
    ],
)
def test_sandbox_recognition_requires_exact_context_and_label(
    monkeypatch: pytest.MonkeyPatch,
    current_context: str,
    namespace_label: str,
    expected: bool,
) -> None:
    environment = object.__new__(KubernetesEnvironment)
    environment.context = "kind-kuber"
    environment.namespace = "kuber-sandbox"
    monkeypatch.setattr(
        environment,
        "_run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, current_context, ""),
    )
    monkeypatch.setattr(
        environment,
        "_kubectl",
        lambda *args, **kwargs: subprocess.CompletedProcess(args, 0, namespace_label, ""),
    )

    assert environment._is_recognized_sandbox() is expected


def test_sandbox_recognition_is_safe_when_kubectl_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    environment = object.__new__(KubernetesEnvironment)
    environment.context = "kind-kuber"
    environment.namespace = "kuber-sandbox"

    def unavailable(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError("kubectl")

    monkeypatch.setattr(environment, "_run", unavailable)
    assert not environment._is_recognized_sandbox()


def test_prepare_sandbox_resets_only_known_resources(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    environment = _live_environment(monkeypatch, tmp_path)
    environment._log_line_cursor = 12
    commands: list[tuple[tuple[str, ...], dict[str, Any]]] = []

    def record(*args: str, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        commands.append((args, kwargs))
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(environment, "_kubectl", record)
    environment.prepare_sandbox()

    flattened = [" ".join(arguments) for arguments, _ in commands]
    assert any("delete role payment-service-sa-kuber-kuber-sandbox" in item for item in flattened)
    assert any("delete job kuber-warmup" in item for item in flattened)
    assert any("apply -f deploy/kind/reference-rbac.yaml" in item for item in flattened)
    assert any("rollout status deployment/payment-service" in item for item in flattened)
    assert environment._log_line_cursor == 0


def test_logs_are_pinned_to_the_fresh_sandbox_pod(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    environment = _live_environment(monkeypatch, tmp_path)
    environment._pod_name = "reference-workload-new"
    arguments: list[tuple[str, ...]] = []

    def record(*args: str, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        arguments.append(args)
        return subprocess.CompletedProcess(args, 0, "events", "")

    monkeypatch.setattr(environment, "_kubectl", record)

    assert environment._logs().startswith("events")
    assert arguments == [("logs", "-n", "kuber-sandbox", "pod/reference-workload-new")]


def test_prepare_sandbox_refuses_dry_run(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(KubernetesEnvironment, "_is_recognized_sandbox", lambda self: False)
    environment = KubernetesEnvironment(artifact_directory=tmp_path)

    with pytest.raises(DryRunOnlyError, match="preparation"):
        environment.prepare_sandbox()


def test_live_apply_and_restore_manage_only_generated_policy(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    environment = _live_environment(monkeypatch, tmp_path)
    commands: list[tuple[tuple[str, ...], dict[str, Any]]] = []

    def record(*args: str, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        commands.append((args, kwargs))
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(environment, "_kubectl", record)
    candidate = Policy(
        (Permission("", "pods", "list", "kuber-sandbox"),),
        name="candidate",
        service_account="payment-service-sa",
        service_account_namespace="kuber-sandbox",
    )

    environment.apply_policy(candidate)
    assert environment.get_current_policy() == candidate
    assert (tmp_path / "payment-service-sa.yaml").exists()
    assert any(arguments[:3] == ("apply", "-f", "-") for arguments, _ in commands)
    assert any(
        arguments[:3] == ("delete", "clusterrolebinding", "payment-service-overprivileged")
        for arguments, _ in commands
    )

    environment.restore_policy()
    assert environment.get_current_policy() == environment._original_policy
    assert environment._candidate_documents == []
    assert any(arguments[:2] == ("delete", "role") for arguments, _ in commands)


def test_dry_run_restore_resets_in_memory_policy(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(KubernetesEnvironment, "_is_recognized_sandbox", lambda self: False)
    environment = KubernetesEnvironment(artifact_directory=tmp_path)
    environment._current_policy = Policy()

    environment.restore_policy()

    assert environment.get_current_policy() == environment._original_policy


def test_observation_collects_structured_events(monkeypatch: pytest.MonkeyPatch) -> None:
    environment = object.__new__(KubernetesEnvironment)
    event = (
        '{"kuber_event":true,"api_group":"","resource":"configmaps",'
        '"verb":"get","namespace":"n","resource_name":"app"}'
    )
    monkeypatch.setattr(environment, "_logs", lambda: f"startup\n{event}\n")

    observed = environment.get_observed_usage()

    assert observed == (KubeEvent("", "configmaps", "get", "n", "app"),)
    assert environment._log_line_cursor == 2


def test_observation_waits_for_delayed_kubernetes_logs(monkeypatch: pytest.MonkeyPatch) -> None:
    environment = object.__new__(KubernetesEnvironment)
    event = (
        '{"kuber_event":true,"api_group":"","resource":"configmaps",'
        '"verb":"get","namespace":"n","resource_name":"app"}'
    )
    values = iter(("startup", "startup", event))
    monkeypatch.setattr(environment, "_logs", lambda: next(values))
    monkeypatch.setattr("kubernetes_runtime.adapter.kubernetes_environment.sleep", lambda _: None)

    assert environment.get_observed_usage() == (KubeEvent("", "configmaps", "get", "n", "app"),)


def test_verification_uses_only_fresh_logs(monkeypatch: pytest.MonkeyPatch) -> None:
    environment = object.__new__(KubernetesEnvironment)
    environment.smoke_command = ("smoke",)
    environment._log_line_cursor = 1
    old_denial = '{"kuber_event":true,"kuber_denied":true,"api_group":"","resource":"secrets","verb":"get","namespace":"n","resource_name":"old"}'
    new_denial = '{"kuber_event":true,"kuber_denied":true,"api_group":"batch","resource":"jobs","verb":"get","namespace":"n","resource_name":"new"}'
    monkeypatch.setattr(
        environment,
        "_run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args[0], 1, "KUBER_TEST_SUMMARY=4/6\n", ""
        ),
    )
    monkeypatch.setattr(environment, "_logs", lambda: f"{old_denial}\n{new_denial}")

    result = environment.verify_workload()

    assert result.tests_passed == 4
    assert result.tests_total == 6
    assert [event.resource_name for event in result.denied_events] == ["new"]


def test_verification_falls_back_to_process_result_without_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    environment = object.__new__(KubernetesEnvironment)
    environment.smoke_command = ("smoke",)
    environment._log_line_cursor = 0
    monkeypatch.setattr(
        environment,
        "_run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, "all good", ""),
    )
    monkeypatch.setattr(environment, "_logs", lambda: "")

    result = environment.verify_workload()

    assert result.passed
    assert (result.tests_passed, result.tests_total) == (6, 6)


def test_failed_verification_waits_for_delayed_denial(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    environment = object.__new__(KubernetesEnvironment)
    environment.smoke_command = ("smoke",)
    environment._log_line_cursor = 1
    denial = (
        '{"kuber_event":true,"kuber_denied":true,"api_group":"batch",'
        '"resource":"jobs","verb":"create","namespace":"n","resource_name":"job"}'
    )
    logs = iter(("startup", "startup", f"startup\n{denial}"))
    monkeypatch.setattr(
        environment,
        "_run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args[0], 1, "KUBER_TEST_SUMMARY=3/6", ""
        ),
    )
    monkeypatch.setattr(environment, "_logs", lambda: next(logs))
    monkeypatch.setattr("kubernetes_runtime.adapter.kubernetes_environment.sleep", lambda _: None)

    result = environment.verify_workload()

    assert [event.resource_name for event in result.denied_events] == ["job"]


def test_failure_description_requires_structured_denial() -> None:
    environment = object.__new__(KubernetesEnvironment)
    denied = KubeEvent("coordination.k8s.io", "leases", "update", "n", "leader")

    mapped = environment.describe_failure(VerificationResult(False, 5, 6, (denied,)))
    unmapped = environment.describe_failure(VerificationResult(False, 0, 6))

    assert mapped.authorization_denial
    assert mapped.missing_events == (denied,)
    assert "1 capability" in mapped.summary
    assert not unmapped.authorization_denial
    assert "automatic repair refused" in unmapped.summary
