from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Self
from uuid import uuid4


class EventType(StrEnum):
    """Versioned domain events shared by Kafka and the deterministic judge."""

    ANALYSIS_REQUESTED = "AnalysisRequested"
    WORKLOAD_OPTIMIZATION_REQUESTED = "WorkloadOptimizationRequested"
    WORKLOAD_OPTIMIZATION_STARTED = "WorkloadOptimizationStarted"
    CANDIDATE_POLICY_GENERATED = "CandidatePolicyGenerated"
    VERIFICATION_FAILED = "VerificationFailed"
    WORKLOAD_OPTIMIZATION_COMPLETED = "WorkloadOptimizationCompleted"
    WORKLOAD_OPTIMIZATION_FAILED = "WorkloadOptimizationFailed"
    SYSTEM_VERIFICATION_REQUESTED = "SystemVerificationRequested"
    SYSTEM_VERIFICATION_COMPLETED = "SystemVerificationCompleted"
    DEPENDENCY_CONTEXT_REQUESTED = "DependencyContextRequested"
    DEAD_LETTERED = "DeadLettered"


@dataclass(frozen=True, slots=True)
class EventEnvelope:
    """Transport-neutral event envelope.

    Payloads contain identifiers and compact context references, never raw source
    repositories or unbounded logs. Unknown payload fields remain forward compatible.
    """

    event_type: EventType
    run_id: str
    correlation_id: str
    payload: dict[str, Any]
    event_id: str = field(default_factory=lambda: uuid4().hex)
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    causation_id: str | None = None
    attempt: int = 0
    schema_version: str = "1"

    def __post_init__(self) -> None:
        for name in ("event_id", "run_id", "correlation_id", "schema_version"):
            if not getattr(self, name):
                raise ValueError(f"{name} must not be empty")
        if self.attempt < 0:
            raise ValueError("attempt must be non-negative")
        if self.schema_version != "1":
            raise ValueError(f"unsupported event schema version: {self.schema_version}")

    @property
    def task_id(self) -> str | None:
        value = self.payload.get("task_id")
        return str(value) if value is not None else None

    @property
    def workload_id(self) -> str | None:
        value = self.payload.get("workload_id")
        return str(value) if value is not None else None

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["event_type"] = self.event_type.value
        return value

    def to_json(self) -> bytes:
        return json.dumps(self.to_dict(), separators=(",", ":"), sort_keys=True).encode()

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Self:
        required = {"event_id", "event_type", "timestamp", "run_id", "correlation_id", "payload"}
        missing = sorted(required.difference(value))
        if missing:
            raise ValueError(f"event is missing required fields: {', '.join(missing)}")
        payload = value["payload"]
        if not isinstance(payload, dict):
            raise ValueError("event payload must be an object")
        return cls(
            event_id=str(value["event_id"]),
            event_type=EventType(str(value["event_type"])),
            timestamp=str(value["timestamp"]),
            run_id=str(value["run_id"]),
            correlation_id=str(value["correlation_id"]),
            causation_id=(str(value["causation_id"]) if value.get("causation_id") else None),
            attempt=int(value.get("attempt", 0)),
            schema_version=str(value.get("schema_version", "1")),
            payload=dict(payload),
        )

    @classmethod
    def from_json(cls, value: bytes | str) -> Self:
        decoded = json.loads(value)
        if not isinstance(decoded, dict):
            raise ValueError("event must be a JSON object")
        return cls.from_dict(decoded)

    def next_attempt(self, *, causation_id: str | None = None) -> Self:
        return type(self)(
            event_type=self.event_type,
            run_id=self.run_id,
            correlation_id=self.correlation_id,
            payload=self.payload,
            causation_id=causation_id or self.event_id,
            attempt=self.attempt + 1,
            schema_version=self.schema_version,
        )
