from typing import Protocol


class KubernetesReader(Protocol):
    def read_config_map(self, name: str) -> dict[str, str]: ...


def load_gateway_routes(client: KubernetesReader) -> dict[str, str]:
    """The gateway reads named routing configuration and performs no mutation."""

    return client.read_config_map("app-config")
