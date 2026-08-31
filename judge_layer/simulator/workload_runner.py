from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from rules_engine.models import KubeEvent, Policy, ServiceAccountRef
from rules_engine.rbac import parse_rbac, resolve_effective_policy


@dataclass(frozen=True, slots=True)
class VerificationTest:
    name: str
    events: tuple[KubeEvent, ...]


@dataclass(frozen=True, slots=True)
class BenchmarkCase:
    identifier: str
    name: str
    description: str
    initial_policy: Policy
    observed_events: tuple[KubeEvent, ...]
    verification_tests: tuple[VerificationTest, ...]
    expected_policy: Policy | None = None


def _load_yaml(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def load_benchmark(path: Path) -> BenchmarkCase:
    metadata = _load_yaml(path / "metadata.yaml")
    if not isinstance(metadata, dict):
        raise ValueError(f"invalid metadata in {path}")
    service_account = ServiceAccountRef(metadata["service_account"], metadata["namespace"])
    initial = resolve_effective_policy(parse_rbac(path / "initial-rbac.yaml"), service_account)
    observed_raw = json.loads((path / "observed-events.json").read_text(encoding="utf-8"))
    observed = tuple(KubeEvent.from_dict(item) for item in observed_raw)
    verification_raw = _load_yaml(path / "verification-tests.yaml")
    tests = tuple(
        VerificationTest(
            item["name"], tuple(KubeEvent.from_dict(event) for event in item["events"])
        )
        for item in verification_raw["tests"]
    )
    expected_path = path / "expected-minimum.yaml"
    expected = (
        resolve_effective_policy(parse_rbac(expected_path), service_account)
        if expected_path.exists() and expected_path.read_text(encoding="utf-8").strip()
        else None
    )
    return BenchmarkCase(
        path.name, metadata["name"], metadata["description"], initial, observed, tests, expected
    )
