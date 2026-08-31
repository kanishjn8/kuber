from __future__ import annotations

import sqlite3
from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver


class SQLiteCheckpointStore:
    """Lifecycle wrapper around LangGraph's lightweight SQLite checkpointer."""

    def __init__(self, path: Path | str) -> None:
        checkpoint_path = Path(path)
        checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(checkpoint_path, check_same_thread=False)
        self.saver = SqliteSaver(self.connection)

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> SQLiteCheckpointStore:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
