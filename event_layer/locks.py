from __future__ import annotations

import asyncio
import importlib
from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Any, Protocol, runtime_checkable


def workload_lock_key(cluster: str, namespace: str, workload_id: str) -> str:
    values = (cluster, namespace, workload_id)
    if any(not value or ":" in value for value in values):
        raise ValueError("lock key components must be non-empty and may not contain ':'")
    return ":".join(values)


@runtime_checkable
class WorkloadLockManager(Protocol):
    def acquire(self, key: str) -> AbstractAsyncContextManager[None]: ...


class InMemoryWorkloadLockManager:
    def __init__(self) -> None:
        self._locks: dict[str, asyncio.Lock] = {}
        self._guard = asyncio.Lock()

    @asynccontextmanager
    async def acquire(self, key: str) -> AsyncIterator[None]:
        async with self._guard:
            lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            yield


class RedisWorkloadLockManager:
    """Redis lease-based lock used only for distributed coordination."""

    def __init__(
        self, redis_url: str, *, timeout_seconds: float = 120, blocking_timeout: float = 30
    ) -> None:
        self.redis_url = redis_url
        self.timeout_seconds = timeout_seconds
        self.blocking_timeout = blocking_timeout
        self._client: Any = None

    async def _get_client(self) -> Any:
        if self._client is None:
            try:
                module = importlib.import_module("redis.asyncio")
            except ModuleNotFoundError as error:
                raise RuntimeError(
                    "Redis locking requires the 'distributed' or 'kubernetes' project extra"
                ) from error
            self._client = module.from_url(self.redis_url, decode_responses=True)
        return self._client

    @asynccontextmanager
    async def acquire(self, key: str) -> AsyncIterator[None]:
        client = await self._get_client()
        lock = client.lock(
            f"kuber:lock:{key}",
            timeout=self.timeout_seconds,
            blocking_timeout=self.blocking_timeout,
        )
        acquired = await lock.acquire()
        if not acquired:
            raise TimeoutError(f"timed out acquiring workload lock: {key}")
        try:
            yield
        finally:
            await lock.release()

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
