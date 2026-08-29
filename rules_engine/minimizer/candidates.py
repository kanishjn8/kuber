from __future__ import annotations

from dataclasses import dataclass

from rules_engine.models import KubeEvent, Permission, Policy
from rules_engine.rbac.authorization import is_authorized
from rules_engine.risk.rules import permission_risk_signals


@dataclass(frozen=True, slots=True)
class CandidateReduction:
    permission: Permission
    reason: str
    risk_value: int


def candidate_reductions(policy: Policy, observed: tuple[KubeEvent, ...]) -> tuple[CandidateReduction, ...]:
    reductions: list[CandidateReduction] = []
    for permission in policy.permissions:
        single = policy.with_permissions([permission])
        if any(is_authorized(single, event) for event in observed):
            continue
        risk = sum(points for _, points in permission_risk_signals(permission))
        reductions.append(CandidateReduction(permission, "not required by observed usage", risk))
    return tuple(
        sorted(
            reductions,
            key=lambda item: (-item.risk_value, *(part or "" for part in item.permission.key())),
        )
    )
