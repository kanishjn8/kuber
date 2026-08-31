from typing import Protocol


class KubernetesWorker(Protocol):
    def read_config_map(self, name: str) -> dict[str, str]: ...
    def create_job(self, name: str) -> None: ...
    def get_job(self, name: str) -> str | None: ...
    def delete_job(self, name: str) -> None: ...


def reconcile(client: KubernetesWorker, name: str) -> str | None:
    """Rare reconciliation uses Job capabilities not exercised by warmup."""

    client.read_config_map("app-config")
    client.create_job(name)
    result = client.get_job(name)
    client.delete_job(name)
    return result
