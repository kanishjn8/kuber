from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from context_layer.models import IndexedServiceContext, ServiceContext
from context_layer.store import ContextStore

_LANGUAGES = {
    ".py": "Python",
    ".go": "Go",
    ".js": "JavaScript",
    ".ts": "TypeScript",
    ".java": "Java",
    ".yaml": "YAML",
    ".yml": "YAML",
}
_IGNORED_PARTS = {".git", ".mypy_cache", ".pytest_cache", ".ruff_cache", ".venv", "__pycache__"}
_ENTRY_NAMES = {"main.py", "app.py", "server.py", "Dockerfile", "pyproject.toml"}


@dataclass(frozen=True, slots=True)
class IndexResult:
    context: IndexedServiceContext
    reused: bool


class ServiceContextIndexer:
    """Hashes and indexes only paths declared for one service."""

    def __init__(self, store: ContextStore, *, maximum_file_bytes: int = 1_000_000) -> None:
        self.store = store
        self.maximum_file_bytes = maximum_file_bytes

    def index(self, service: ServiceContext) -> IndexResult:
        root = Path(service.source_repository.local_path).resolve()
        files = self._resolve_files(root, service.important_paths)
        digest = hashlib.sha256()
        bytes_loaded = 0
        languages: set[str] = set()
        usage = set(service.kubernetes_usage)
        entry_points: list[str] = []

        for path in files:
            relative = path.relative_to(root).as_posix()
            content = path.read_bytes()
            digest.update(relative.encode())
            digest.update(b"\0")
            digest.update(content)
            bytes_loaded += len(content)
            language = _LANGUAGES.get(path.suffix.lower())
            if language:
                languages.add(language)
            if path.name in _ENTRY_NAMES:
                entry_points.append(relative)
            lowered = content.lower()
            if b"kubernetes" in lowered or b"kubectl" in lowered or b"client-go" in lowered:
                usage.add(relative)

        content_hash = digest.hexdigest()
        previous = self.store.latest(service.service_id)
        if previous is not None and previous.content_hash == content_hash:
            return IndexResult(previous, reused=True)

        context = IndexedServiceContext(
            context_ref=f"context://{service.service_id}/{content_hash[:16]}",
            service_id=service.service_id,
            content_hash=content_hash,
            files=tuple(path.relative_to(root).as_posix() for path in files),
            bytes_loaded=bytes_loaded,
            languages=tuple(sorted(languages)),
            kubernetes_usage=tuple(sorted(usage)),
            dependencies=tuple(sorted(set(service.dependencies))),
            entry_points=tuple(sorted(entry_points)),
        )
        self.store.put(context)
        return IndexResult(context, reused=False)

    def _resolve_files(self, root: Path, important_paths: tuple[str, ...]) -> tuple[Path, ...]:
        if not root.is_dir():
            raise FileNotFoundError(f"service repository does not exist: {root}")
        selected: set[Path] = set()
        for relative in important_paths:
            candidate = (root / relative).resolve()
            if not candidate.is_relative_to(root):
                raise ValueError(f"important path escapes repository root: {relative}")
            paths = candidate.rglob("*") if candidate.is_dir() else (candidate,)
            for path in paths:
                if (
                    path.is_file()
                    and not _IGNORED_PARTS.intersection(path.parts)
                    and path.stat().st_size <= self.maximum_file_bytes
                ):
                    selected.add(path)
        return tuple(sorted(selected))
