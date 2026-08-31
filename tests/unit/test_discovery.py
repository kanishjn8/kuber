from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from context_layer.discovery import KubernetesServiceDiscovery


def deployment(name: str, *, opted_in: bool) -> SimpleNamespace:
    annotations = (
        {
            "kuber.dev/source-path": f"examples/service_catalog/{name.replace('-', '_')}",
            "kuber.dev/important-paths": "service.py,service-context.yaml",
            "kuber.dev/verification-profile": name,
            "kuber.dev/dependencies": "order-service",
            "kuber.dev/repository-url": "https://example.invalid/repository.git",
            "kuber.dev/commit-sha": "abc123",
        }
        if opted_in
        else {}
    )
    return SimpleNamespace(
        metadata=SimpleNamespace(
            name=name,
            labels={"app.kubernetes.io/name": name},
            annotations=annotations,
        ),
        spec=SimpleNamespace(
            template=SimpleNamespace(
                spec=SimpleNamespace(
                    service_account_name=f"{name}-sa",
                    containers=[SimpleNamespace(image=f"{name}:dev")],
                )
            )
        ),
    )


def test_kubernetes_discovery_selects_only_annotated_workloads(tmp_path: Path) -> None:
    api = SimpleNamespace(
        list_namespaced_deployment=lambda namespace: SimpleNamespace(
            items=[
                deployment("payment-service", opted_in=True),
                deployment("kafka", opted_in=False),
            ]
        )
    )
    discovery = KubernetesServiceDiscovery(repository_root=tmp_path, api=api)

    services = discovery.discover("kuber-sandbox")

    assert len(services) == 1
    service = services[0]
    assert service.service_id == "payment-service"
    assert service.service_account == "payment-service-sa"
    assert service.dependencies == ("order-service",)
    assert service.source_repository.remote_url == "https://example.invalid/repository.git"
    assert service.source_repository.commit_sha == "abc123"
    assert service.container_images == ("payment-service:dev",)
