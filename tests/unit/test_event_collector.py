from kubernetes_runtime.observation import collect_events


def test_collects_normalized_and_denied_events_from_prefixed_logs() -> None:
    logs = """
INFO kuber.events {"kuber_event": true, "api_group": "", "resource": "pods", "verb": "list", "namespace": "n", "resource_name": null}
noise that is not JSON
ERROR kuber.events {"kuber_event": true, "kuber_denied": true, "api_group": "batch", "resource": "jobs", "verb": "create", "namespace": "n", "resource_name": "j"}
"""
    assert len(collect_events(logs)) == 2
    denied = collect_events(logs, denied_only=True)
    assert len(denied) == 1
    assert denied[0].resource == "jobs"
