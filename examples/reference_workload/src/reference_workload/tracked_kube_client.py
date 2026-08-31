"""Instrumented wrappers around the real in-cluster Kubernetes client."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any, TypeVar

from kubernetes import client, config
from kubernetes.client.exceptions import ApiException

T = TypeVar("T")


class TrackedKubeClient:
    """Thin instrumentation around real in-cluster Kubernetes API calls."""

    def __init__(self, namespace: str, workload_id: str | None = None) -> None:
        config.load_incluster_config()
        self.namespace = namespace
        self.workload_id = workload_id
        self.core = client.CoreV1Api()
        self.batch = client.BatchV1Api()
        self.coordination = client.CoordinationV1Api()

    def _event(
        self, api_group: str, resource: str, verb: str, resource_name: str | None = None
    ) -> dict[str, Any]:
        value = {
            "kuber_event": True,
            "api_group": api_group,
            "resource": resource,
            "verb": verb,
            "namespace": self.namespace,
            "resource_name": resource_name,
        }
        workload_id = getattr(self, "workload_id", None)
        if workload_id:
            value["workload_id"] = workload_id
        return value

    def _call(self, event: dict[str, Any], operation: Callable[[], T]) -> T:
        # Use stdout directly rather than an application logger. Uvicorn's
        # default logging configuration can suppress custom INFO loggers, while
        # container stdout is always available to `kubectl logs`.
        print(json.dumps(event, sort_keys=True), flush=True)
        try:
            return operation()
        except ApiException as exc:
            if exc.status == 403:
                print(
                    json.dumps(
                        {**event, "kuber_denied": True, "message": exc.reason},
                        sort_keys=True,
                    ),
                    flush=True,
                )
            raise

    def read_config_map(self, name: str) -> dict[str, str]:
        event = self._event("", "configmaps", "get", name)
        value = self._call(
            event, lambda: self.core.read_namespaced_config_map(name, self.namespace)
        )
        return value.data or {}

    def read_secret(self, name: str) -> dict[str, str]:
        event = self._event("", "secrets", "get", name)
        value = self._call(event, lambda: self.core.read_namespaced_secret(name, self.namespace))
        return value.data or {}

    def list_pods(self) -> list[str]:
        event = self._event("", "pods", "list")
        value = self._call(event, lambda: self.core.list_namespaced_pod(self.namespace))
        return [item.metadata.name for item in value.items]

    def create_job(self, name: str) -> None:
        event = self._event("batch", "jobs", "create", name)
        body = client.V1Job(
            metadata=client.V1ObjectMeta(name=name),
            spec=client.V1JobSpec(
                template=client.V1PodTemplateSpec(
                    metadata=client.V1ObjectMeta(labels={"app": name}),
                    spec=client.V1PodSpec(
                        restart_policy="Never",
                        containers=[
                            client.V1Container(
                                name="reconcile",
                                image="busybox:1.36",
                                command=["sh", "-c", "echo reconciled"],
                            )
                        ],
                    ),
                ),
                backoff_limit=0,
            ),
        )
        try:
            self._call(event, lambda: self.batch.create_namespaced_job(self.namespace, body))
        except ApiException as exc:
            # A prior verification attempt can leave the deterministic smoke
            # Job behind after a later call was denied. Reconciliation is idempotent.
            if exc.status != 409:
                raise

    def get_job(self, name: str) -> str | None:
        event = self._event("batch", "jobs", "get", name)
        value = self._call(event, lambda: self.batch.read_namespaced_job(name, self.namespace))
        job_name: object = value.metadata.name
        return job_name if isinstance(job_name, str) else None

    def delete_job(self, name: str) -> None:
        event = self._event("batch", "jobs", "delete", name)
        self._call(
            event,
            lambda: self.batch.delete_namespaced_job(
                name, self.namespace, propagation_policy="Background"
            ),
        )

    def renew_leader_lease(self, name: str) -> str:
        """Legitimate low-frequency path intentionally excluded from warmup."""

        read_event = self._event("coordination.k8s.io", "leases", "get", name)
        try:
            lease = self._call(
                read_event, lambda: self.coordination.read_namespaced_lease(name, self.namespace)
            )
            update_event = self._event("coordination.k8s.io", "leases", "update", name)
            self._call(
                update_event,
                lambda: self.coordination.replace_namespaced_lease(name, self.namespace, lease),
            )
            return "updated"
        except ApiException as exc:
            if exc.status != 404:
                raise
        create_event = self._event("coordination.k8s.io", "leases", "create", name)
        body = client.V1Lease(
            metadata=client.V1ObjectMeta(name=name),
            spec=client.V1LeaseSpec(holder_identity="kuber-reference-workload"),
        )
        lease = self._call(
            create_event,
            lambda: self.coordination.create_namespaced_lease(self.namespace, body),
        )
        # The full smoke behavior proves both initial acquisition and renewal.
        # Returning immediately after create would allow a policy that fails on
        # the controller's very next leader-election cycle.
        update_event = self._event("coordination.k8s.io", "leases", "update", name)
        self._call(
            update_event,
            lambda: self.coordination.replace_namespaced_lease(name, self.namespace, lease),
        )
        return "created-and-renewed"
