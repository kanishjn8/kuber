from __future__ import annotations

from types import SimpleNamespace

import pytest

from context_layer import IndexedServiceContext
from event_layer import EventEnvelope, EventType
from kubernetes_runtime.adapter.factory import KubernetesEnvironmentFactory


def test_factory_routes_event_to_guarded_service_environment(monkeypatch) -> None:
    captured: dict[str, object] = {}
    monkeypatch.setattr(
        "kubernetes_runtime.adapter.factory.KubernetesEnvironment",
        lambda **kwargs: captured.update(kwargs) or SimpleNamespace(**kwargs),
    )
    event = EventEnvelope(
        EventType.WORKLOAD_OPTIMIZATION_REQUESTED,
        run_id="run",
        correlation_id="run",
        payload={
            "workload_id": "payment-service",
            "namespace": "kuber-sandbox",
            "service_account": "payment-service-sa",
            "deployment": "payment-service",
        },
    )
    context = IndexedServiceContext(
        "context://payment-service/hash",
        "payment-service",
        "hash",
        (),
        0,
        (),
        (),
        (),
        (),
    )
    result = KubernetesEnvironmentFactory().create(event, context)

    assert result.service_account == "payment-service-sa"
    assert captured["smoke_command"] == (
        "./deploy/kind/scripts/service-smoke.sh",
        "payment-service",
    )

    wrong = IndexedServiceContext("context://other/hash", "other", "hash", (), 0, (), (), (), ())
    with pytest.raises(ValueError, match="identifiers differ"):
        KubernetesEnvironmentFactory().create(event, wrong)
