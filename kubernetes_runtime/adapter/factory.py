from __future__ import annotations

from pathlib import Path

from context_layer import IndexedServiceContext
from event_layer import EventEnvelope
from kubernetes_runtime.adapter.kubernetes_environment import KubernetesEnvironment


class KubernetesEnvironmentFactory:
    """Builds one guarded live adapter from a discovered workload event."""

    def __init__(
        self,
        *,
        context: str = "kind-kuber",
        artifact_directory: Path = Path("artifacts/policies"),
    ) -> None:
        self.context = context
        self.artifact_directory = artifact_directory

    def create(self, event: EventEnvelope, context: IndexedServiceContext) -> KubernetesEnvironment:
        payload = event.payload
        workload_id = str(payload["workload_id"])
        if workload_id != context.service_id:
            raise ValueError("event and service context workload identifiers differ")
        return KubernetesEnvironment(
            context=self.context,
            namespace=str(payload["namespace"]),
            service_account=str(payload["service_account"]),
            deployment_name=str(payload["deployment"]),
            workload_id=workload_id,
            smoke_command=("./deploy/kind/scripts/service-smoke.sh", workload_id),
            initial_manifest=Path("deploy/kind/reference-rbac.yaml"),
            original_binding_name=f"{workload_id}-overprivileged",
            artifact_directory=self.artifact_directory,
        )
