from __future__ import annotations

from dataclasses import dataclass, field

from rules_engine.models.policy import PolicyRule
from rules_engine.models.workload import ServiceAccountRef


@dataclass(frozen=True, slots=True)
class ServiceAccountObject:
    name: str
    namespace: str


@dataclass(frozen=True, slots=True)
class RoleObject:
    name: str
    namespace: str | None
    rules: tuple[PolicyRule, ...]
    cluster_role: bool = False


@dataclass(frozen=True, slots=True)
class BindingObject:
    name: str
    namespace: str | None
    role_name: str
    role_kind: str
    subjects: tuple[ServiceAccountRef, ...]
    cluster_binding: bool = False


@dataclass(frozen=True, slots=True)
class ParsedRbac:
    service_accounts: tuple[ServiceAccountObject, ...] = field(default_factory=tuple)
    roles: tuple[RoleObject, ...] = field(default_factory=tuple)
    bindings: tuple[BindingObject, ...] = field(default_factory=tuple)
