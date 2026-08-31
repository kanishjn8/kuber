from __future__ import annotations

from pathlib import Path

import pytest

from context_layer import (
    RepositorySource,
    ServiceContext,
    ServiceContextIndexer,
    SQLiteContextStore,
    SQLiteServiceRegistry,
)


def service(root: Path) -> ServiceContext:
    return ServiceContext(
        service_id="payment-service",
        namespace="kuber-sandbox",
        workload_kind="Deployment",
        deployment_name="payment-service",
        service_account="payment-sa",
        source_repository=RepositorySource("payment-service", str(root)),
        important_paths=("src", "deployment.yaml"),
        verification_profile="payment-service",
        dependencies=("order-service",),
    )


def test_registry_and_scoped_incremental_context_index(tmp_path: Path) -> None:
    repository = tmp_path / "payment"
    (repository / "src").mkdir(parents=True)
    (repository / "src/main.py").write_text("from kubernetes import client\n", encoding="utf-8")
    (repository / "deployment.yaml").write_text("kind: Deployment\n", encoding="utf-8")
    (repository / "unrelated.txt").write_text("must not be loaded\n", encoding="utf-8")
    database = tmp_path / "context.sqlite"
    registry = SQLiteServiceRegistry(database)
    store = SQLiteContextStore(database)
    item = service(repository)
    registry.put(item)

    indexer = ServiceContextIndexer(store)
    first = indexer.index(item)
    second = indexer.index(item)
    assert registry.get("payment-service") == item
    assert registry.list(namespace="kuber-sandbox") == (item,)
    assert first.reused is False
    assert second.reused is True
    assert first.context.files == ("deployment.yaml", "src/main.py")
    assert "unrelated.txt" not in first.context.files
    assert first.context.context_ref.startswith("context://payment-service/")
    assert first.context.kubernetes_usage == ("src/main.py",)
    assert store.get(first.context.context_ref) == first.context

    (repository / "src/main.py").write_text("print('changed')\n", encoding="utf-8")
    changed = indexer.index(item)
    assert not changed.reused
    assert changed.context.content_hash != first.context.content_hash
    registry.close()
    store.close()


def test_indexer_rejects_paths_outside_service_root(tmp_path: Path) -> None:
    repository = tmp_path / "service"
    repository.mkdir()
    outside = tmp_path / "secret.txt"
    outside.write_text("secret", encoding="utf-8")
    store = SQLiteContextStore(tmp_path / "context.sqlite")
    unsafe = ServiceContext(
        **{
            **service(repository).to_dict(),
            "source_repository": RepositorySource("payment-service", str(repository)),
            "important_paths": ("../secret.txt",),
        }
    )
    with pytest.raises(ValueError, match="escapes"):
        ServiceContextIndexer(store).index(unsafe)
    store.close()
