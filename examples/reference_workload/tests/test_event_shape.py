import json
from types import SimpleNamespace
from typing import Any

import pytest
from kubernetes import client as kubernetes_client
from kubernetes import config as kubernetes_config
from kubernetes.client.exceptions import ApiException
from reference_workload.tracked_kube_client import TrackedKubeClient


def test_normalized_event_shape_without_cluster_connection() -> None:
    client = object.__new__(TrackedKubeClient)
    client.namespace = "payments"
    assert client._event("", "configmaps", "get", "app-config") == {
        "kuber_event": True,
        "api_group": "",
        "resource": "configmaps",
        "verb": "get",
        "namespace": "payments",
        "resource_name": "app-config",
    }


def test_normalized_event_includes_workload_identity_when_configured() -> None:
    client = object.__new__(TrackedKubeClient)
    client.namespace = "payments"
    client.workload_id = "payment-service"

    assert client._event("", "pods", "list")["workload_id"] == "payment-service"


def test_call_always_emits_successful_event(capsys: pytest.CaptureFixture[str]) -> None:
    client = object.__new__(TrackedKubeClient)
    event = {
        "kuber_event": True,
        "api_group": "",
        "resource": "pods",
        "verb": "list",
        "namespace": "payments",
        "resource_name": None,
    }

    assert client._call(event, lambda: "ok") == "ok"
    assert json.loads(capsys.readouterr().out) == event


def test_call_marks_real_403_as_denied(capsys: pytest.CaptureFixture[str]) -> None:
    client = object.__new__(TrackedKubeClient)
    event = {
        "kuber_event": True,
        "api_group": "batch",
        "resource": "jobs",
        "verb": "create",
        "namespace": "payments",
        "resource_name": "job-1",
    }

    with pytest.raises(ApiException):
        client._call(
            event, lambda: (_ for _ in ()).throw(ApiException(status=403, reason="Forbidden"))
        )

    emitted = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert emitted[0] == event
    assert emitted[1]["kuber_denied"] is True


def test_client_initializes_all_in_cluster_api_clients(monkeypatch: pytest.MonkeyPatch) -> None:
    loaded: list[bool] = []
    monkeypatch.setattr(kubernetes_config, "load_incluster_config", lambda: loaded.append(True))
    monkeypatch.setattr(kubernetes_client, "CoreV1Api", lambda: "core")
    monkeypatch.setattr(kubernetes_client, "BatchV1Api", lambda: "batch")
    monkeypatch.setattr(kubernetes_client, "CoordinationV1Api", lambda: "coordination")

    tracked = TrackedKubeClient("payments")

    assert loaded == [True]
    assert (tracked.core, tracked.batch, tracked.coordination) == ("core", "batch", "coordination")


def test_core_and_job_wrappers_return_normalized_values(capsys: pytest.CaptureFixture[str]) -> None:
    tracked = object.__new__(TrackedKubeClient)
    tracked.namespace = "payments"
    calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []

    class Core:
        def read_namespaced_config_map(self, *args: Any, **kwargs: Any) -> Any:
            calls.append(("config", args, kwargs))
            return SimpleNamespace(data={"mode": "sandbox"})

        def read_namespaced_secret(self, *args: Any, **kwargs: Any) -> Any:
            calls.append(("secret", args, kwargs))
            return SimpleNamespace(data={"token": "encoded"})

        def list_namespaced_pod(self, *args: Any, **kwargs: Any) -> Any:
            calls.append(("pods", args, kwargs))
            return SimpleNamespace(items=[SimpleNamespace(metadata=SimpleNamespace(name="pod-1"))])

    class Batch:
        def create_namespaced_job(self, *args: Any, **kwargs: Any) -> None:
            calls.append(("create", args, kwargs))

        def read_namespaced_job(self, *args: Any, **kwargs: Any) -> Any:
            calls.append(("get", args, kwargs))
            return SimpleNamespace(metadata=SimpleNamespace(name="job-1"))

        def delete_namespaced_job(self, *args: Any, **kwargs: Any) -> None:
            calls.append(("delete", args, kwargs))

    tracked.core = Core()
    tracked.batch = Batch()

    assert tracked.read_config_map("app-config") == {"mode": "sandbox"}
    assert tracked.read_secret("payment-secret") == {"token": "encoded"}
    assert tracked.list_pods() == ["pod-1"]
    tracked.create_job("job-1")
    assert tracked.get_job("job-1") == "job-1"
    tracked.delete_job("job-1")

    assert [name for name, _, _ in calls] == ["config", "secret", "pods", "create", "get", "delete"]
    assert len(capsys.readouterr().out.splitlines()) == 6


@pytest.mark.parametrize("status", [409, 500])
def test_create_job_only_tolerates_existing_job(
    status: int, capsys: pytest.CaptureFixture[str]
) -> None:
    tracked = object.__new__(TrackedKubeClient)
    tracked.namespace = "payments"

    class FailingBatch:
        def create_namespaced_job(self, *args: Any, **kwargs: Any) -> None:
            raise ApiException(status=status)

    tracked.batch = FailingBatch()

    if status == 409:
        tracked.create_job("job-1")
    else:
        with pytest.raises(ApiException):
            tracked.create_job("job-1")
    assert capsys.readouterr().out


@pytest.mark.parametrize(
    ("existing", "expected"), [(True, "updated"), (False, "created-and-renewed")]
)
def test_leader_lease_handles_existing_and_first_acquisition(
    existing: bool, expected: str, capsys: pytest.CaptureFixture[str]
) -> None:
    tracked = object.__new__(TrackedKubeClient)
    tracked.namespace = "payments"
    operations: list[str] = []
    lease = SimpleNamespace(metadata=SimpleNamespace(name="kuber-reference-leader"))

    class Coordination:
        def read_namespaced_lease(self, *args: Any, **kwargs: Any) -> Any:
            operations.append("get")
            if not existing:
                raise ApiException(status=404)
            return lease

        def create_namespaced_lease(self, *args: Any, **kwargs: Any) -> Any:
            operations.append("create")
            return lease

        def replace_namespaced_lease(self, *args: Any, **kwargs: Any) -> Any:
            operations.append("update")
            return lease

    tracked.coordination = Coordination()

    assert tracked.renew_leader_lease("kuber-reference-leader") == expected
    assert operations == (["get", "update"] if existing else ["get", "create", "update"])
    assert capsys.readouterr().out


def test_leader_lease_propagates_non_not_found_error(capsys: pytest.CaptureFixture[str]) -> None:
    tracked = object.__new__(TrackedKubeClient)
    tracked.namespace = "payments"

    class Coordination:
        def read_namespaced_lease(self, *args: Any, **kwargs: Any) -> None:
            raise ApiException(status=403)

    tracked.coordination = Coordination()

    with pytest.raises(ApiException):
        tracked.renew_leader_lease("kuber-reference-leader")
    assert "kuber_denied" in capsys.readouterr().out
