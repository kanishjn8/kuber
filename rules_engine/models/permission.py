from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, order=True, slots=True)
class Permission:
    """One normalized RBAC capability.

    ``namespace=None`` means cluster-wide. Wildcards are retained so breadth is
    visible to the authorization and risk engines.
    """

    api_group: str
    resource: str
    verb: str
    namespace: str | None = None
    resource_name: str | None = None
    source: str | None = None

    def key(self, *, include_source: bool = False) -> tuple[str | None, ...]:
        parts: tuple[str | None, ...] = (
            self.api_group,
            self.resource,
            self.verb,
            self.namespace,
            self.resource_name,
        )
        return (*parts, self.source) if include_source else parts

    def display(self) -> str:
        group = self.api_group or "core"
        scope = self.namespace or "cluster-wide"
        name = f"/{self.resource_name}" if self.resource_name else ""
        return f"{self.verb} {group}/{self.resource}{name} ({scope})"

