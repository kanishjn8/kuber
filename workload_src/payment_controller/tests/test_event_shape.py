from src.tracked_kube_client import TrackedKubeClient


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

