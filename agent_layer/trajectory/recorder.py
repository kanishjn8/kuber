from __future__ import annotations

import json
from pathlib import Path

from agent_layer.trajectory.models import TrajectoryEvent


class TrajectoryRecorder:
    def __init__(self, run_id: str, directory: Path | None = None) -> None:
        self.run_id = run_id
        self.directory = directory
        self.events: list[TrajectoryEvent] = []
        self._started = False

    def record(self, event: TrajectoryEvent) -> None:
        self.events.append(event)
        if self.directory is not None:
            self.directory.mkdir(parents=True, exist_ok=True)
            path = self.directory / f"{self.run_id}.jsonl"
            with path.open("a" if self._started else "w", encoding="utf-8") as handle:
                handle.write(json.dumps(event.to_dict(), sort_keys=True) + "\n")
            self._started = True

    def write_summary(self) -> Path | None:
        if self.directory is None:
            return None
        path = self.directory / f"{self.run_id}.md"
        lines = [f"# Kuber trajectory: {self.run_id}", ""]
        lines.extend(
            f"{index}. **{event.agent} / {event.action}** — {event.reason}"
            + (f" Decision: `{event.decision}`." if event.decision else "")
            for index, event in enumerate(self.events, 1)
        )
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return path
