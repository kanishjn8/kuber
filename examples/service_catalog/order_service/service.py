from typing import Protocol


class KubernetesReader(Protocol):
    def read_config_map(self, name: str) -> dict[str, str]: ...


def load_order_configuration(client: KubernetesReader) -> dict[str, str]:
    """Order handling only needs its named configuration."""

    return client.read_config_map("app-config")
