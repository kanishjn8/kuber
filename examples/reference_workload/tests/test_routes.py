from __future__ import annotations

from typing import Any

import pytest
from fastapi import HTTPException
from kubernetes.client.exceptions import ApiException
from reference_workload import main


class FakeKubeClient:
    def read_config_map(self, name: str) -> dict[str, str]:
        assert name == "app-config"
        return {"mode": "sandbox"}

    def read_secret(self, name: str) -> dict[str, str]:
        assert name in {"auth-secret", "payment-secret"}
        return {"token": "encoded", "account": "encoded"}

    def list_pods(self) -> list[str]:
        return ["reference-workload-1"]

    def create_job(self, name: str) -> None:
        assert name in {"invoice-1", "kuber-worker-smoke"}

    def get_job(self, name: str) -> str:
        return name

    def delete_job(self, name: str) -> None:
        assert name in {"invoice-1", "kuber-worker-smoke"}

    def renew_leader_lease(self, name: str) -> str:
        assert name == "kuber-reference-leader"
        return "updated"


def test_all_workload_routes_delegate_to_tracked_client(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeKubeClient()
    monkeypatch.setattr(main, "kube", lambda: fake)

    assert main.health() == {"status": "ok"}
    assert main.config() == {"data": {"mode": "sandbox"}}
    assert main.secret() == {"keys": ["account", "token"]}
    assert main.pods() == {"pods": ["reference-workload-1"]}
    assert main.reconcile("invoice-1") == {"job": "invoice-1", "status": "reconciled"}
    assert main.leader_election() == {"status": "updated"}


@pytest.mark.parametrize(
    ("service_id", "expected_keys"),
    [
        ("api-gateway", {"service", "config"}),
        ("auth-service", {"service", "config", "secret_keys"}),
        ("order-service", {"service", "config"}),
        ("payment-service", {"service", "config", "secret_keys", "pods"}),
        ("worker-service", {"service", "config"}),
    ],
)
def test_service_profiles_exercise_distinct_kubernetes_needs(
    monkeypatch: pytest.MonkeyPatch, service_id: str, expected_keys: set[str]
) -> None:
    monkeypatch.setattr(main, "SERVICE_ID", service_id)
    monkeypatch.setattr(main, "kube", lambda: FakeKubeClient())

    assert set(main.profile()) == expected_keys


def test_worker_rare_workflow_is_owner_scoped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(main, "SERVICE_ID", "worker-service")
    monkeypatch.setattr(main, "kube", lambda: FakeKubeClient())
    assert main.rare_workflow() == {"job": "kuber-worker-smoke", "status": "reconciled"}

    monkeypatch.setattr(main, "SERVICE_ID", "auth-service")
    with pytest.raises(HTTPException) as raised:
        main.rare_workflow()
    assert raised.value.status_code == 404


@pytest.mark.parametrize(
    ("route", "method"),
    [
        (main.config, "read_config_map"),
        (main.secret, "read_secret"),
        (main.pods, "list_pods"),
        (lambda: main.reconcile("invoice-1"), "create_job"),
        (main.leader_election, "renew_leader_lease"),
    ],
)
def test_routes_translate_kubernetes_errors(
    monkeypatch: pytest.MonkeyPatch, route: Any, method: str
) -> None:
    fake = FakeKubeClient()

    def denied(*args: object) -> None:
        raise ApiException(status=403, reason="Forbidden")

    monkeypatch.setattr(fake, method, denied)
    monkeypatch.setattr(main, "kube", lambda: fake)

    with pytest.raises(HTTPException) as raised:
        route()

    assert raised.value.status_code == 403
    assert raised.value.detail == "Forbidden"


def test_kubernetes_error_defaults_are_safe() -> None:
    translated = main._forbidden(ApiException())

    assert translated.status_code == 500
    assert translated.detail == "Kubernetes API failure"
