from __future__ import annotations

import subprocess
from pathlib import Path
from time import perf_counter

from agent_layer.interfaces import FailureDescription, VerificationResult
from demo_layer.observation import collect_events
from rules_engine.models import KubeEvent, Policy, ServiceAccountRef
from rules_engine.rbac import parse_rbac, policy_to_documents, policy_to_yaml, resolve_effective_policy


class SafetyError(RuntimeError):
    pass


class DryRunOnlyError(SafetyError):
    pass


class KubernetesEnvironment:
    """Live adapter guarded to the labeled ``kind-kuber`` sandbox by default."""

    def __init__(
        self,
        *,
        context: str = "kind-kuber",
        namespace: str = "kuber-demo",
        service_account: str = "payment-controller",
        smoke_command: tuple[str, ...] = ("./demo_layer/scripts/smoke-test.sh",),
        dry_run: bool | None = None,
        allow_unsafe_context: bool = False,
        artifact_directory: Path = Path("artifacts/policies"),
    ) -> None:
        self.context = context
        self.namespace = namespace
        self.service_account = service_account
        self.smoke_command = smoke_command
        self.allow_unsafe_context = allow_unsafe_context
        self.artifact_directory = artifact_directory
        self._initial_manifest = Path("demo_layer/kubernetes/overprivileged-rbac.yaml")
        parsed = parse_rbac(self._initial_manifest)
        self._original_policy = resolve_effective_policy(parsed, ServiceAccountRef(service_account, namespace))
        self._current_policy = self._original_policy
        self._candidate_documents: list[dict[str, object]] = []
        self._safe = self._is_recognized_sandbox()
        self.dry_run = (not self._safe) if dry_run is None else dry_run
        if not self._safe and not self.dry_run and not allow_unsafe_context:
            raise SafetyError("live mutation refused: context and sandbox namespace label were not both recognized")

    @property
    def name(self) -> str:
        mode = "dry-run" if self.dry_run else "live"
        return f"kubernetes:{self.context}/{self.namespace}:{mode}"

    def _run(self, command: tuple[str, ...], *, input_text: str | None = None, check: bool = True, timeout: int = 90) -> subprocess.CompletedProcess[str]:
        return subprocess.run(command, input=input_text, text=True, capture_output=True, check=check, timeout=timeout)

    def _kubectl(self, *arguments: str, input_text: str | None = None, check: bool = True, timeout: int = 90) -> subprocess.CompletedProcess[str]:
        return self._run(("kubectl", "--context", self.context, *arguments), input_text=input_text, check=check, timeout=timeout)

    def _is_recognized_sandbox(self) -> bool:
        try:
            current = self._run(("kubectl", "config", "current-context"), timeout=10).stdout.strip()
            if current != self.context or self.context != "kind-kuber":
                return False
            label = self._kubectl("get", "namespace", self.namespace, "-o", "jsonpath={.metadata.labels.kuber\\.dev/sandbox}", timeout=10).stdout.strip()
            return label == "true"
        except (FileNotFoundError, subprocess.SubprocessError):
            return False

    def get_current_policy(self) -> Policy:
        return self._current_policy

    def _logs(self) -> str:
        result = self._kubectl("logs", "-n", self.namespace, "deployment/payment-controller", check=False, timeout=30)
        return f"{result.stdout}\n{result.stderr}"

    def get_observed_usage(self) -> tuple[KubeEvent, ...]:
        return collect_events(self._logs())

    def apply_policy(self, policy: Policy) -> None:
        yaml_text = policy_to_yaml(policy)
        # Parse and resolve generated YAML before it can reach kubectl.
        validated = resolve_effective_policy(parse_rbac(yaml_text), ServiceAccountRef(self.service_account, self.namespace))
        if {item.key() for item in validated.permissions} != {item.key() for item in policy.permissions}:
            raise ValueError("generated policy failed deterministic round-trip validation")
        self.artifact_directory.mkdir(parents=True, exist_ok=True)
        proposal = self.artifact_directory / f"{self.service_account}.yaml"
        proposal.write_text(yaml_text, encoding="utf-8")
        if self.dry_run:
            raise DryRunOnlyError(f"proposal written to {proposal}; explicit approval is required outside the sandbox")
        self._candidate_documents = policy_to_documents(policy)
        if self._candidate_documents:
            self._kubectl("apply", "-f", "-", input_text=yaml_text)
        # Remove only the exact known demo overprivileged binding. The role is
        # harmless without a binding and is retained for fast reset.
        self._kubectl("delete", "clusterrolebinding", "payment-controller-overprivileged", "--ignore-not-found")
        self._current_policy = policy

    def verify_workload(self) -> VerificationResult:
        started = perf_counter()
        result = self._run(self.smoke_command, check=False, timeout=120)
        logs = self._logs()
        denied = collect_events(logs, denied_only=True)
        total = 6
        passed = total if result.returncode == 0 else max(0, total - max(1, len(denied)))
        return VerificationResult(
            result.returncode == 0,
            passed,
            total,
            denied,
            result.stdout,
            f"{result.stderr}\n{logs}",
            perf_counter() - started,
        )

    def _delete_candidates(self) -> None:
        for document in self._candidate_documents:
            kind = str(document["kind"]).lower()
            metadata = document["metadata"]
            assert isinstance(metadata, dict)
            name = str(metadata["name"])
            arguments = ["delete", kind, name, "--ignore-not-found"]
            if metadata.get("namespace"):
                arguments.extend(("-n", str(metadata["namespace"])))
            self._kubectl(*arguments, check=False)
        self._candidate_documents = []

    def restore_policy(self) -> None:
        if self.dry_run:
            self._current_policy = self._original_policy
            return
        self._delete_candidates()
        self._kubectl("apply", "-f", str(self._initial_manifest))
        self._current_policy = self._original_policy

    def describe_failure(self, result: VerificationResult) -> FailureDescription:
        if result.denied_events:
            return FailureDescription(
                f"real Kubernetes RBAC denied {len(result.denied_events)} capability/capabilities",
                result.denied_events,
                True,
            )
        return FailureDescription("smoke tests failed without a structured Kubernetes 403; automatic repair refused")
