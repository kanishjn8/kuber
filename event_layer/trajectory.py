from __future__ import annotations

import json
from pathlib import Path
from threading import Lock

from event_layer.bus import ConsumedEvent, PublishedEvent


class EventTrajectoryRecorder:
    """Append-only transport trajectory separated from graph checkpoints."""

    def __init__(self, root: Path = Path("artifacts/trajectories")) -> None:
        self.root = root
        self._lock = Lock()

    def __call__(self, stage: str, message: PublishedEvent) -> None:
        event = message.event
        workload_id = event.workload_id or "system"
        directory = self.root / event.run_id
        directory.mkdir(parents=True, exist_ok=True)
        value = {
            "stage": stage,
            "topic": message.topic,
            "key": message.key,
            "partition": message.partition,
            "offset": message.offset,
            "event": event.to_dict(),
        }
        if isinstance(message, ConsumedEvent):
            value.update(
                {
                    "consumer_group": message.consumer_group,
                    "consumer_id": message.consumer_id,
                    "delivery_count": message.delivery_count,
                }
            )
        path = directory / f"{workload_id}-events.jsonl"
        with self._lock, path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(value, separators=(",", ":"), sort_keys=True) + "\n")
