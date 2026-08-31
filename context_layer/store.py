from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Protocol, runtime_checkable

from context_layer.models import IndexedServiceContext, ServiceContext


@runtime_checkable
class ServiceRegistry(Protocol):
    def put(self, service: ServiceContext) -> None: ...

    def get(self, service_id: str) -> ServiceContext | None: ...

    def list(self, *, namespace: str | None = None) -> tuple[ServiceContext, ...]: ...


@runtime_checkable
class ContextStore(Protocol):
    def put(self, context: IndexedServiceContext) -> None: ...

    def get(self, context_ref: str) -> IndexedServiceContext | None: ...

    def latest(self, service_id: str) -> IndexedServiceContext | None: ...


class _SQLiteStore:
    def __init__(self, path: Path | str) -> None:
        self.path = str(path)
        self.connection = sqlite3.connect(self.path, check_same_thread=False)
        self.connection.execute("PRAGMA journal_mode=WAL")

    def close(self) -> None:
        self.connection.close()


class SQLiteServiceRegistry(_SQLiteStore):
    def __init__(self, path: Path | str) -> None:
        super().__init__(path)
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS services (
                service_id TEXT PRIMARY KEY,
                namespace TEXT NOT NULL,
                record TEXT NOT NULL
            )
            """
        )
        self.connection.commit()

    def put(self, service: ServiceContext) -> None:
        record = json.dumps(service.to_dict(), separators=(",", ":"), sort_keys=True)
        self.connection.execute(
            "INSERT OR REPLACE INTO services(service_id, namespace, record) VALUES (?, ?, ?)",
            (service.service_id, service.namespace, record),
        )
        self.connection.commit()

    def get(self, service_id: str) -> ServiceContext | None:
        row = self.connection.execute(
            "SELECT record FROM services WHERE service_id = ?", (service_id,)
        ).fetchone()
        return ServiceContext.from_dict(json.loads(row[0])) if row else None

    def list(self, *, namespace: str | None = None) -> tuple[ServiceContext, ...]:
        if namespace is None:
            rows = self.connection.execute("SELECT record FROM services ORDER BY service_id")
        else:
            rows = self.connection.execute(
                "SELECT record FROM services WHERE namespace = ? ORDER BY service_id", (namespace,)
            )
        return tuple(ServiceContext.from_dict(json.loads(row[0])) for row in rows)


class SQLiteContextStore(_SQLiteStore):
    def __init__(self, path: Path | str) -> None:
        super().__init__(path)
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS service_contexts (
                context_ref TEXT PRIMARY KEY,
                service_id TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                record TEXT NOT NULL
            )
            """
        )
        self.connection.execute(
            "CREATE INDEX IF NOT EXISTS context_service_idx "
            "ON service_contexts(service_id, created_at DESC)"
        )
        self.connection.commit()

    def put(self, context: IndexedServiceContext) -> None:
        record = json.dumps(context.to_dict(), separators=(",", ":"), sort_keys=True)
        self.connection.execute(
            "INSERT OR REPLACE INTO service_contexts(context_ref, service_id, record) "
            "VALUES (?, ?, ?)",
            (context.context_ref, context.service_id, record),
        )
        self.connection.commit()

    def get(self, context_ref: str) -> IndexedServiceContext | None:
        row = self.connection.execute(
            "SELECT record FROM service_contexts WHERE context_ref = ?", (context_ref,)
        ).fetchone()
        return IndexedServiceContext.from_dict(json.loads(row[0])) if row else None

    def latest(self, service_id: str) -> IndexedServiceContext | None:
        row = self.connection.execute(
            "SELECT record FROM service_contexts WHERE service_id = ? "
            "ORDER BY created_at DESC, rowid DESC LIMIT 1",
            (service_id,),
        ).fetchone()
        return IndexedServiceContext.from_dict(json.loads(row[0])) if row else None
