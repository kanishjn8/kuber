from __future__ import annotations

import importlib
import json
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class DeduplicationStore(Protocol):
    async def get(self, task_id: str) -> dict[str, Any] | None: ...

    async def put(self, task_id: str, result: dict[str, Any]) -> None: ...


class InMemoryDeduplicationStore:
    def __init__(self) -> None:
        self._results: dict[str, dict[str, Any]] = {}

    async def get(self, task_id: str) -> dict[str, Any] | None:
        result = self._results.get(task_id)
        return dict(result) if result is not None else None

    async def put(self, task_id: str, result: dict[str, Any]) -> None:
        self._results[task_id] = dict(result)


class RedisDeduplicationStore:
    def __init__(self, redis_url: str, *, ttl_seconds: int = 86_400) -> None:
        self.redis_url = redis_url
        self.ttl_seconds = ttl_seconds
        self._client: Any = None

    async def _get_client(self) -> Any:
        if self._client is None:
            try:
                module = importlib.import_module("redis.asyncio")
            except ModuleNotFoundError as error:
                raise RuntimeError(
                    "Redis deduplication requires the 'distributed' or 'kubernetes' project extra"
                ) from error
            self._client = module.from_url(self.redis_url, decode_responses=True)
        return self._client

    async def get(self, task_id: str) -> dict[str, Any] | None:
        value = await (await self._get_client()).get(f"kuber:completed:{task_id}")
        if value is None:
            return None
        decoded = json.loads(value)
        if not isinstance(decoded, dict):
            raise ValueError("deduplication result is not an object")
        return decoded

    async def put(self, task_id: str, result: dict[str, Any]) -> None:
        await (await self._get_client()).set(
            f"kuber:completed:{task_id}",
            json.dumps(result, separators=(",", ":"), sort_keys=True),
            ex=self.ttl_seconds,
        )

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
