from __future__ import annotations

import importlib
from collections.abc import Iterable
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from context_layer.models import RepositorySource, ServiceContext


@runtime_checkable
class ServiceDiscovery(Protocol):
    def discover(self, namespace: str) -> tuple[ServiceContext, ...]: ...


class StaticServiceDiscovery:
    """Deterministic discovery implementation used by judge benchmarks."""

    def __init__(self, services: Iterable[ServiceContext]) -> None:
        self.services = tuple(services)

    def discover(self, namespace: str) -> tuple[ServiceContext, ...]:
        return tuple(service for service in self.services if service.namespace == namespace)


class KubernetesServiceDiscovery:
    """Discovers deployments dynamically and reads source routing from annotations."""

    def __init__(
        self,
        *,
        repository_root: Path = Path("."),
        context: str = "kind-kuber",
        api: Any = None,
    ) -> None:
        self.repository_root = repository_root.resolve()
        self.context = context
        self._api = api

    def _get_api(self) -> Any:
        if self._api is None:
            try:
                client = importlib.import_module("kubernetes.client")
                config = importlib.import_module("kubernetes.config")
            except ModuleNotFoundError as error:
                raise RuntimeError(
                    "Kubernetes discovery requires the 'kubernetes' project extra"
                ) from error
            config.load_kube_config(context=self.context)
            self._api = client.AppsV1Api()
        return self._api

    def discover(self, namespace: str) -> tuple[ServiceContext, ...]:
        deployments = self._get_api().list_namespaced_deployment(namespace).items
        opted_in = (
            item
            for item in deployments
            if "kuber.dev/source-path" in dict(item.metadata.annotations or {})
        )
        return tuple(
            sorted(
                (self._to_context(item, namespace) for item in opted_in), key=lambda x: x.service_id
            )
        )

    def _to_context(self, deployment: Any, namespace: str) -> ServiceContext:
        metadata = deployment.metadata
        pod_spec = deployment.spec.template.spec
        labels = dict(metadata.labels or {})
        annotations = dict(metadata.annotations or {})
        service_id = labels.get("app.kubernetes.io/name", metadata.name)
        source_path = annotations.get(
            "kuber.dev/source-path", f"examples/service_catalog/{service_id}"
        )
        important_paths = tuple(
            value.strip()
            for value in annotations.get("kuber.dev/important-paths", ".").split(",")
            if value.strip()
        )
        dependencies = tuple(
            value.strip()
            for value in annotations.get("kuber.dev/dependencies", "").split(",")
            if value.strip()
        )
        return ServiceContext(
            service_id=service_id,
            namespace=namespace,
            workload_kind="Deployment",
            deployment_name=metadata.name,
            service_account=pod_spec.service_account_name or "default",
            source_repository=RepositorySource(
                service_id=service_id,
                local_path=str((self.repository_root / source_path).resolve()),
                remote_url=annotations.get("kuber.dev/repository-url"),
                commit_sha=annotations.get("kuber.dev/commit-sha"),
            ),
            important_paths=important_paths,
            verification_profile=annotations.get("kuber.dev/verification-profile", service_id),
            labels=labels,
            container_images=tuple(container.image for container in pod_spec.containers),
            dependencies=dependencies,
            last_indexed_commit=annotations.get("kuber.dev/commit-sha"),
        )
