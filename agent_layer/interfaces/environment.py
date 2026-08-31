from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from rules_engine.models import KubeEvent, Policy


@dataclass(frozen=True, slots=True)
class VerificationResult:
    passed: bool
    tests_passed: int
    tests_total: int
    denied_events: tuple[KubeEvent, ...] = field(default_factory=tuple)
    stdout: str = ""
    stderr: str = ""
    duration_seconds: float = 0.0


@dataclass(frozen=True, slots=True)
class FailureDescription:
    summary: str
    missing_events: tuple[KubeEvent, ...] = field(default_factory=tuple)
    authorization_denial: bool = False


@runtime_checkable
class EnvironmentAdapter(Protocol):
    """The only environment-facing API used by Kuber's agent layer."""

    @property
    def name(self) -> str: ...

    def get_current_policy(self) -> Policy: ...

    def get_observed_usage(self) -> tuple[KubeEvent, ...]: ...

    def apply_policy(self, policy: Policy) -> None: ...

    def verify_workload(self) -> VerificationResult: ...

    def restore_policy(self) -> None: ...

    def describe_failure(self, result: VerificationResult) -> FailureDescription: ...
