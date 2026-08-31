from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Self


@dataclass(frozen=True, slots=True)
class RepositorySource:
    service_id: str
    local_path: str
    remote_url: str | None = None
    commit_sha: str | None = None

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Self:
        return cls(
            service_id=str(value["service_id"]),
            local_path=str(value["local_path"]),
            remote_url=str(value["remote_url"]) if value.get("remote_url") else None,
            commit_sha=str(value["commit_sha"]) if value.get("commit_sha") else None,
        )


@dataclass(frozen=True, slots=True)
class ServiceContext:
    service_id: str
    namespace: str
    workload_kind: str
    deployment_name: str
    service_account: str
    source_repository: RepositorySource
    important_paths: tuple[str, ...]
    verification_profile: str
    labels: dict[str, str] = field(default_factory=dict)
    container_images: tuple[str, ...] = ()
    kubernetes_usage: tuple[str, ...] = ()
    dependencies: tuple[str, ...] = ()
    last_indexed_commit: str | None = None

    def __post_init__(self) -> None:
        if self.source_repository.service_id != self.service_id:
            raise ValueError("repository service_id must match service context")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Self:
        repository = value["source_repository"]
        if not isinstance(repository, dict):
            raise ValueError("source_repository must be an object")
        return cls(
            service_id=str(value["service_id"]),
            namespace=str(value["namespace"]),
            workload_kind=str(value["workload_kind"]),
            deployment_name=str(value["deployment_name"]),
            service_account=str(value["service_account"]),
            source_repository=RepositorySource.from_dict(repository),
            important_paths=tuple(map(str, value.get("important_paths", ()))),
            verification_profile=str(value["verification_profile"]),
            labels={str(key): str(item) for key, item in dict(value.get("labels", {})).items()},
            container_images=tuple(map(str, value.get("container_images", ()))),
            kubernetes_usage=tuple(map(str, value.get("kubernetes_usage", ()))),
            dependencies=tuple(map(str, value.get("dependencies", ()))),
            last_indexed_commit=(
                str(value["last_indexed_commit"]) if value.get("last_indexed_commit") else None
            ),
        )


@dataclass(frozen=True, slots=True)
class IndexedServiceContext:
    context_ref: str
    service_id: str
    content_hash: str
    files: tuple[str, ...]
    bytes_loaded: int
    languages: tuple[str, ...]
    kubernetes_usage: tuple[str, ...]
    dependencies: tuple[str, ...]
    entry_points: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Self:
        return cls(
            context_ref=str(value["context_ref"]),
            service_id=str(value["service_id"]),
            content_hash=str(value["content_hash"]),
            files=tuple(map(str, value.get("files", ()))),
            bytes_loaded=int(value.get("bytes_loaded", 0)),
            languages=tuple(map(str, value.get("languages", ()))),
            kubernetes_usage=tuple(map(str, value.get("kubernetes_usage", ()))),
            dependencies=tuple(map(str, value.get("dependencies", ()))),
            entry_points=tuple(map(str, value.get("entry_points", ()))),
        )
