from __future__ import annotations

import re
import subprocess
from pathlib import Path
from time import perf_counter, sleep

from agent_layer.interfaces import FailureDescription, VerificationResult
from kubernetes_runtime.observation import collect_events
from rules_engine.models import KubeEvent, Policy, ServiceAccountRef
from rules_engine.rbac import (
    parse_rbac,
    policy_to_documents,
    policy_to_yaml,
    resolve_effective_policy,
)


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
        namespace: str = "kuber-sandbox",
        service_account: str = "payment-service-sa",
        deployment_name: str = "payment-service",
        workload_id: str = "payment-service",
        smoke_command: tuple[str, ...] = (
            "./deploy/kind/scripts/service-smoke.sh",
            "payment-service",
        ),
        initial_manifest: Path = Path("deploy/kind/reference-rbac.yaml"),
        original_binding_name: str = "payment-service-overprivileged",
        dry_run: bool | None = None,
        allow_unsafe_context: bool = False,
        artifact_directory: Path = Path("artifacts/policies"),
    ) -> None:
        self.context = context
        self.namespace = namespace
        self.service_account = service_account
        self.deployment_name = deployment_name
        self.workload_id = workload_id
        self.smoke_command = smoke_command
        self.original_binding_name = original_binding_name
        self.allow_unsafe_context = allow_unsafe_context
        self.artifact_directory = artifact_directory
        self._initial_manifest = initial_manifest
        parsed = parse_rbac(self._initial_manifest)
        self._original_policy = resolve_effective_policy(
            parsed, ServiceAccountRef(service_account, namespace)
        )
        self._current_policy = self._original_policy
        self._candidate_documents: list[dict[str, object]] = []
        self._log_line_cursor = 0
        self._pod_name: str | None = None
        self._safe = self._is_recognized_sandbox()
        self.dry_run = (not self._safe) if dry_run is None else dry_run
        if not self._safe and not self.dry_run and not allow_unsafe_context:
            raise SafetyError(
                "live mutation refused: context and sandbox namespace label were not both recognized"
            )

    @property
    def name(self) -> str:
        mode = "dry-run" if self.dry_run else "live"
        return f"kubernetes:{self.context}/{self.namespace}:{self.workload_id}:{mode}"

    def _run(
        self,
        command: tuple[str, ...],
        *,
        input_text: str | None = None,
        check: bool = True,
        timeout: int = 90,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            command, input=input_text, text=True, capture_output=True, check=check, timeout=timeout
        )

    def _kubectl(
        self, *arguments: str, input_text: str | None = None, check: bool = True, timeout: int = 90
    ) -> subprocess.CompletedProcess[str]:
        return self._run(
            ("kubectl", "--context", self.context, *arguments),
            input_text=input_text,
            check=check,
            timeout=timeout,
        )

    def _is_recognized_sandbox(self) -> bool:
        try:
            current = self._run(("kubectl", "config", "current-context"), timeout=10).stdout.strip()
            if current != self.context or self.context != "kind-kuber":
                return False
            label = self._kubectl(
                "get",
                "namespace",
                self.namespace,
                "-o",
                "jsonpath={.metadata.labels.kuber\\.dev/sandbox}",
                timeout=10,
            ).stdout.strip()
            return label == "true"
        except (FileNotFoundError, subprocess.SubprocessError):
            return False

    def get_current_policy(self) -> Policy:
        return self._current_policy

    def _logs(self) -> str:
        target = f"pod/{self._pod_name}" if self._pod_name else f"deployment/{self.deployment_name}"
        result = self._kubectl("logs", "-n", self.namespace, target, check=False, timeout=30)
        return f"{result.stdout}\n{result.stderr}"

    def get_observed_usage(self) -> tuple[KubeEvent, ...]:
        # Container stdout can lag briefly behind the completed HTTP request in
        # the Kubernetes logs API. Poll within a small bound so an empty first
        # read cannot produce an unsafe empty candidate.
        deadline = perf_counter() + 5
        logs = ""
        events: tuple[KubeEvent, ...] = ()
        while perf_counter() < deadline:
            logs = self._logs()
            events = collect_events(logs)
            if events:
                break
            sleep(0.2)
        self._log_line_cursor = len(logs.splitlines())
        return events

    def prepare_sandbox(self) -> None:
        """Reset only known reference resources and start with fresh workload logs."""

        if self.dry_run:
            raise DryRunOnlyError("live preparation requires the recognized sandbox")
        self._delete_candidates()
        # A new CLI process cannot remember documents applied by an older run,
        # so remove the exact deterministic names that Kuber generates here.
        known = (
            (
                "rolebinding",
                f"{self.service_account}-kuber-{self.namespace}-binding",
                True,
            ),
            ("role", f"{self.service_account}-kuber-{self.namespace}", True),
            (
                "clusterrolebinding",
                f"{self.service_account}-kuber-cluster-binding",
                False,
            ),
            ("clusterrole", f"{self.service_account}-kuber-cluster", False),
        )
        for kind, name, namespaced in known:
            arguments = ["delete", kind, name, "--ignore-not-found"]
            if namespaced:
                arguments.extend(("-n", self.namespace))
            self._kubectl(*arguments, check=False)
        for job_name in ("kuber-warmup", "kuber-smoke", "kuber-worker-smoke"):
            self._kubectl(
                "delete",
                "job",
                job_name,
                "-n",
                self.namespace,
                "--ignore-not-found",
                check=False,
            )
        self._kubectl(
            "delete",
            "lease",
            self.deployment_name,
            "-n",
            self.namespace,
            "--ignore-not-found",
            check=False,
        )
        self._kubectl("apply", "-f", str(self._initial_manifest))
        self._kubectl(
            "rollout", "restart", f"deployment/{self.deployment_name}", "-n", self.namespace
        )
        self._kubectl(
            "rollout",
            "status",
            f"deployment/{self.deployment_name}",
            "-n",
            self.namespace,
            "--timeout=120s",
            timeout=130,
        )
        # Pin all evidence reads to the newest running pod. Asking kubectl for
        # deployment logs during rollout can select an older terminating pod
        # and contaminate a new run with stale observations.
        pod = self._kubectl(
            "get",
            "pods",
            "-n",
            self.namespace,
            "-l",
            f"app={self.deployment_name}",
            "--field-selector=status.phase=Running",
            "--sort-by=.metadata.creationTimestamp",
            "-o",
            "jsonpath={.items[-1].metadata.name}",
            check=False,
        ).stdout.strip()
        self._pod_name = pod or None
        self._current_policy = self._original_policy
        self._log_line_cursor = 0

    def apply_policy(self, policy: Policy) -> None:
        yaml_text = policy_to_yaml(policy)
        # Parse and resolve generated YAML before it can reach kubectl.
        validated = resolve_effective_policy(
            parse_rbac(yaml_text), ServiceAccountRef(self.service_account, self.namespace)
        )
        if {item.key() for item in validated.permissions} != {
            item.key() for item in policy.permissions
        }:
            raise ValueError("generated policy failed deterministic round-trip validation")
        self.artifact_directory.mkdir(parents=True, exist_ok=True)
        proposal = self.artifact_directory / f"{self.service_account}.yaml"
        proposal.write_text(yaml_text, encoding="utf-8")
        if self.dry_run:
            raise DryRunOnlyError(
                f"proposal written to {proposal}; explicit approval is required outside the sandbox"
            )
        self._candidate_documents = policy_to_documents(policy)
        if self._candidate_documents:
            self._kubectl("apply", "-f", "-", input_text=yaml_text)
        # Remove only the exact known reference overprivileged binding. The role is
        # harmless without a binding and is retained for fast reset.
        for kind in ("rolebinding", "clusterrolebinding"):
            arguments = ["delete", kind, self.original_binding_name, "--ignore-not-found"]
            if kind == "rolebinding":
                arguments.extend(("-n", self.namespace))
            self._kubectl(*arguments)
        self._current_policy = policy

    def verify_workload(self) -> VerificationResult:
        started = perf_counter()
        result = self._run(self.smoke_command, check=False, timeout=120)
        # On failure, wait briefly for the structured 403 line that explains
        # the failed request. Successful tests need no denial evidence.
        deadline = perf_counter() + 5
        lines: list[str] = []
        fresh_logs = ""
        denied: tuple[KubeEvent, ...] = ()
        while perf_counter() < deadline:
            logs = self._logs()
            lines = logs.splitlines()
            start = self._log_line_cursor if self._log_line_cursor <= len(lines) else 0
            fresh_logs = "\n".join(lines[start:])
            denied = collect_events(fresh_logs, denied_only=True)
            if result.returncode == 0 or denied:
                break
            sleep(0.2)
        self._log_line_cursor = len(lines)
        total = 6
        summary = re.search(r"KUBER_TEST_SUMMARY=(\d+)/(\d+)", result.stdout)
        passed = int(summary.group(1)) if summary else (total if result.returncode == 0 else 0)
        total = int(summary.group(2)) if summary else total
        return VerificationResult(
            result.returncode == 0,
            passed,
            total,
            denied,
            result.stdout,
            f"{result.stderr}\n{fresh_logs}",
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
        self._kubectl("apply", "-f", "-", input_text=policy_to_yaml(self._original_policy))
        self._current_policy = self._original_policy

    def describe_failure(self, result: VerificationResult) -> FailureDescription:
        if result.denied_events:
            return FailureDescription(
                f"real Kubernetes RBAC denied {len(result.denied_events)} capability/capabilities",
                result.denied_events,
                True,
            )
        return FailureDescription(
            "smoke tests failed without a structured Kubernetes 403; automatic repair refused"
        )
