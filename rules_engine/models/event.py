from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True, order=True, slots=True)
class KubeEvent:
    api_group: str
    resource: str
    verb: str
    namespace: str | None = None
    resource_name: str | None = None

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "KubeEvent":
        return cls(
            api_group=str(value.get("api_group", "")),
            resource=str(value["resource"]),
            verb=str(value["verb"]),
            namespace=value.get("namespace"),
            resource_name=value.get("resource_name"),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def display(self) -> str:
        group = self.api_group or "core"
        name = f"/{self.resource_name}" if self.resource_name else ""
        return f"{self.verb} {group}/{self.resource}{name}"

