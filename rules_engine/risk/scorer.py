from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from rules_engine.models import Policy
from rules_engine.risk.rules import permission_risk_signals


@dataclass(frozen=True, slots=True)
class RiskFinding:
    reason: str
    points: int
    occurrences: int


@dataclass(frozen=True, slots=True)
class RiskAssessment:
    score: int
    uncapped_score: int
    findings: tuple[RiskFinding, ...]
    heuristic: str = "Kuber benchmark heuristic v1 (not an industry standard)"


def score_policy(policy: Policy) -> RiskAssessment:
    totals: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for permission in policy.permissions:
        for reason, points in permission_risk_signals(permission):
            totals[reason][0] += points
            totals[reason][1] += 1
    findings = tuple(
        RiskFinding(reason, values[0], values[1])
        for reason, values in sorted(totals.items(), key=lambda item: (-item[1][0], item[0]))
    )
    uncapped = sum(finding.points for finding in findings)
    return RiskAssessment(min(100, uncapped), uncapped, findings)
