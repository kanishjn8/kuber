from typing import Protocol


class KubernetesReader(Protocol):
    def read_config_map(self, name: str) -> dict[str, str]: ...
    def read_secret(self, name: str) -> dict[str, str]: ...
    def list_pods(self) -> list[str]: ...


def load_payment_runtime(client: KubernetesReader) -> dict[str, object]:
    """Payments read one Secret, shared configuration, and Pod status."""

    return {
        "config": client.read_config_map("app-config"),
        "credentials": client.read_secret("payment-secret"),
        "pods": client.list_pods(),
    }
