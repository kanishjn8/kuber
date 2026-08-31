from typing import Protocol


class KubernetesReader(Protocol):
    def read_config_map(self, name: str) -> dict[str, str]: ...
    def read_secret(self, name: str) -> dict[str, str]: ...


def load_auth_material(client: KubernetesReader) -> tuple[dict[str, str], dict[str, str]]:
    """Authentication needs one named Secret and shared non-secret configuration."""

    return client.read_config_map("app-config"), client.read_secret("auth-secret")
