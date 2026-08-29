from __future__ import annotations

import json

from rules_engine.models import KubeEvent


def collect_events(log_text: str, *, denied_only: bool = False) -> tuple[KubeEvent, ...]:
    events: dict[KubeEvent, None] = {}
    for line in log_text.splitlines():
        candidate = line[line.find("{") :] if "{" in line else ""
        try:
            value = json.loads(candidate)
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(value, dict) or value.get("kuber_event") is not True:
            continue
        if denied_only and value.get("kuber_denied") is not True:
            continue
        try:
            events[KubeEvent.from_dict(value)] = None
        except (KeyError, TypeError, ValueError):
            continue
    return tuple(events)

