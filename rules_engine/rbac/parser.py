from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

import yaml

from rules_engine.models import (
    BindingObject,
    ParsedRbac,
    PolicyRule,
    RoleObject,
    ServiceAccountObject,
    ServiceAccountRef,
)
from rules_engine.rbac.canonicalizer import SUPPORTED_VERBS, is_supported_resource


class RbacParseError(ValueError):
    pass


class UnsupportedResourceError(RbacParseError):
    pass


def _strings(value: Any, field: str, *, allow_empty_string: bool = False) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise RbacParseError(f"{field} must be a non-empty list")
    if not all(isinstance(item, str) for item in value):
        raise RbacParseError(f"{field} entries must be strings")
    if not allow_empty_string and any(not item for item in value):
        raise RbacParseError(f"{field} entries must not be empty")
    return tuple(value)


def _metadata(document: Mapping[str, Any]) -> tuple[str, str | None]:
    metadata = document.get("metadata")
    if not isinstance(metadata, Mapping) or not isinstance(metadata.get("name"), str):
        raise RbacParseError("every RBAC object requires metadata.name")
    namespace = metadata.get("namespace")
    if namespace is not None and not isinstance(namespace, str):
        raise RbacParseError("metadata.namespace must be a string")
    return metadata["name"], namespace


def _rules(value: Any) -> tuple[PolicyRule, ...]:
    if not isinstance(value, list):
        raise RbacParseError("rules must be a list")
    result: list[PolicyRule] = []
    for raw in value:
        if not isinstance(raw, Mapping):
            raise RbacParseError("each rule must be a mapping")
        api_groups = _strings(raw.get("apiGroups", [""]), "apiGroups", allow_empty_string=True)
        resources = _strings(raw.get("resources"), "resources")
        verbs = _strings(raw.get("verbs"), "verbs")
        resource_names = tuple(raw.get("resourceNames", ()))
        if not all(isinstance(item, str) and item for item in resource_names):
            raise RbacParseError("resourceNames entries must be non-empty strings")
        for verb in verbs:
            if verb != "*" and verb not in SUPPORTED_VERBS:
                raise RbacParseError(f"unsupported verb: {verb}")
        for group in api_groups:
            for resource in resources:
                if not is_supported_resource(group, resource):
                    raise UnsupportedResourceError(f"unsupported resource: {group or 'core'}/{resource}")
        result.append(PolicyRule(api_groups, resources, verbs, resource_names))
    return tuple(result)


def _flatten_documents(documents: Iterable[Any]) -> list[Mapping[str, Any]]:
    flattened: list[Mapping[str, Any]] = []
    for document in documents:
        if document is None:
            continue
        if not isinstance(document, Mapping):
            raise RbacParseError("YAML documents must be mappings")
        if document.get("kind") == "List":
            items = document.get("items")
            if not isinstance(items, list):
                raise RbacParseError("List.items must be a list")
            flattened.extend(_flatten_documents(items))
        else:
            flattened.append(document)
    return flattened


def parse_rbac(source: str | Path | Iterable[Mapping[str, Any]]) -> ParsedRbac:
    """Parse the intentionally supported RBAC subset and reject ambiguous input."""

    try:
        if isinstance(source, Path):
            raw_documents = list(yaml.safe_load_all(source.read_text(encoding="utf-8")))
        elif isinstance(source, str):
            path = Path(source)
            if "\n" not in source and path.exists():
                raw_documents = list(yaml.safe_load_all(path.read_text(encoding="utf-8")))
            else:
                raw_documents = list(yaml.safe_load_all(source))
        else:
            raw_documents = list(source)
    except (OSError, yaml.YAMLError) as exc:
        raise RbacParseError(f"invalid RBAC YAML: {exc}") from exc

    service_accounts: list[ServiceAccountObject] = []
    roles: list[RoleObject] = []
    bindings: list[BindingObject] = []
    supported_kinds = {"ServiceAccount", "Role", "ClusterRole", "RoleBinding", "ClusterRoleBinding"}
    for document in _flatten_documents(raw_documents):
        kind = document.get("kind")
        if kind not in supported_kinds:
            raise RbacParseError(f"unsupported RBAC kind: {kind}")
        name, namespace = _metadata(document)
        if kind == "ServiceAccount":
            if not namespace:
                raise RbacParseError("ServiceAccount requires metadata.namespace")
            service_accounts.append(ServiceAccountObject(name, namespace))
        elif kind in {"Role", "ClusterRole"}:
            if kind == "Role" and not namespace:
                raise RbacParseError("Role requires metadata.namespace")
            roles.append(RoleObject(name, namespace if kind == "Role" else None, _rules(document.get("rules", [])), kind == "ClusterRole"))
        else:
            if kind == "RoleBinding" and not namespace:
                raise RbacParseError("RoleBinding requires metadata.namespace")
            role_ref = document.get("roleRef")
            if not isinstance(role_ref, Mapping) or role_ref.get("kind") not in {"Role", "ClusterRole"} or not isinstance(role_ref.get("name"), str):
                raise RbacParseError("binding requires a valid roleRef")
            subjects: list[ServiceAccountRef] = []
            for subject in document.get("subjects", []):
                if not isinstance(subject, Mapping):
                    raise RbacParseError("binding subjects must be mappings")
                if subject.get("kind") != "ServiceAccount":
                    continue
                subject_name = subject.get("name")
                subject_namespace = subject.get("namespace") or namespace
                if not isinstance(subject_name, str) or not isinstance(subject_namespace, str):
                    raise RbacParseError("ServiceAccount subjects require name and namespace")
                subjects.append(ServiceAccountRef(subject_name, subject_namespace))
            bindings.append(
                BindingObject(
                    name=name,
                    namespace=namespace if kind == "RoleBinding" else None,
                    role_name=role_ref["name"],
                    role_kind=role_ref["kind"],
                    subjects=tuple(subjects),
                    cluster_binding=kind == "ClusterRoleBinding",
                )
            )
    return ParsedRbac(tuple(service_accounts), tuple(roles), tuple(bindings))

