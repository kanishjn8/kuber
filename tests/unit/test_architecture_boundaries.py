from __future__ import annotations

import ast
from pathlib import Path


def _imports_under(root: Path) -> set[str]:
    imports: set[str] = set()
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module)
    return imports


def test_rules_engine_has_no_environment_or_llm_dependencies() -> None:
    imports = _imports_under(Path("rules_engine"))
    forbidden = (
        "agent_layer",
        "context_layer",
        "kubernetes_runtime",
        "docker",
        "event_layer",
        "google",
        "judge_layer",
        "kafka",
        "kubernetes",
        "langgraph",
        "redis",
    )
    assert not {name for name in imports if name.startswith(forbidden)}


def test_agent_layer_depends_only_on_rules_and_its_interfaces() -> None:
    imports = _imports_under(Path("agent_layer"))
    forbidden = ("judge_layer", "kubernetes_runtime", "kubernetes", "docker")
    assert not {name for name in imports if name.startswith(forbidden)}
