from __future__ import annotations

from dataclasses import dataclass, field

from rules_engine.models.permission import Permission


@dataclass(frozen=True, slots=True)
class PolicyRule:
    api_groups: tuple[str, ...]
    resources: tuple[str, ...]
    verbs: tuple[str, ...]
    resource_names: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Policy:
    permissions: tuple[Permission, ...] = field(default_factory=tuple)
    name: str = "policy"
    service_account: str = "default"
    service_account_namespace: str = "default"

    def __post_init__(self) -> None:
        unique = {permission.key(): permission for permission in self.permissions}
        ordered = tuple(
            sorted(
                unique.values(),
                key=lambda item: tuple(part or "" for part in item.key()),
            )
        )
        object.__setattr__(self, "permissions", ordered)

    def with_permissions(self, permissions: list[Permission] | tuple[Permission, ...]) -> "Policy":
        return Policy(
            permissions=tuple(permissions),
            name=self.name,
            service_account=self.service_account,
            service_account_namespace=self.service_account_namespace,
        )
