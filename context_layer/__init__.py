"""Persistent service registry and compact service-scoped context storage."""

from context_layer.discovery import (
    KubernetesServiceDiscovery,
    ServiceDiscovery,
    StaticServiceDiscovery,
)
from context_layer.indexer import IndexResult, ServiceContextIndexer
from context_layer.models import IndexedServiceContext, RepositorySource, ServiceContext
from context_layer.store import (
    ContextStore,
    ServiceRegistry,
    SQLiteContextStore,
    SQLiteServiceRegistry,
)

__all__ = [
    "ContextStore",
    "IndexResult",
    "IndexedServiceContext",
    "KubernetesServiceDiscovery",
    "RepositorySource",
    "SQLiteContextStore",
    "SQLiteServiceRegistry",
    "ServiceContext",
    "ServiceContextIndexer",
    "ServiceDiscovery",
    "ServiceRegistry",
    "StaticServiceDiscovery",
]
