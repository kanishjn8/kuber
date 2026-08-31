from __future__ import annotations

import os
import re
from pathlib import Path

import yaml


def test_sandbox_manifests_are_valid_yaml_objects() -> None:
    manifests = sorted(Path("deploy/kind").glob("*.yaml"))
    assert manifests
    for path in manifests:
        documents = list(yaml.safe_load_all(path.read_text(encoding="utf-8")))
        assert documents, path
        for document in documents:
            assert isinstance(document, dict), path
            assert document.get("apiVersion"), path
            assert document.get("kind"), path
            if document["apiVersion"].startswith("kind.x-k8s.io/"):
                continue
            assert document.get("metadata", {}).get("name"), path


def test_sandbox_scripts_are_executable_and_syntax_checked_by_quality_workflow() -> None:
    scripts = sorted(Path("deploy/kind/scripts").glob("*.sh"))
    assert scripts
    assert all(os.access(script, os.X_OK) for script in scripts)
    assert all("rg " not in script.read_text(encoding="utf-8") for script in scripts)


def test_kafka_setup_filters_only_the_known_topic_metric_warning() -> None:
    setup = Path("deploy/kind/scripts/setup.sh").read_text(encoding="utf-8")
    assert '[[ "$line" != "WARNING: Due to limitations in metric names,"* ]]' in setup
    assert "printf '%s\\n' \"$output\" >&2" in setup
    topics = re.findall(r"^  (kuber\.[a-z.]+)(?: \\|; do)$", setup, flags=re.MULTILINE)
    assert len(topics) == 6
    assert all("_" not in topic for topic in topics)


def test_public_environment_example_contains_no_secret() -> None:
    values = {}
    for line in Path(".env.example").read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#"):
            key, value = line.split("=", 1)
            values[key] = value
    assert set(values) == {"GEMINI_API_KEY", "GEMINI_MODEL", "GEMINI_TIMEOUT_SECONDS"}
    assert values["GEMINI_API_KEY"] == "your_gemini_api_key_here"
    assert values["GEMINI_MODEL"] == "gemini-3.1-flash-lite"


def test_sandbox_workload_has_restricted_container_security() -> None:
    namespace = yaml.safe_load(Path("deploy/kind/namespace.yaml").read_text(encoding="utf-8"))
    documents = list(
        yaml.safe_load_all(Path("deploy/kind/workloads.yaml").read_text(encoding="utf-8"))
    )
    deployments = [item for item in documents if item["kind"] == "Deployment"]
    labels = namespace["metadata"]["labels"]
    assert labels["kuber.dev/sandbox"] == "true"
    assert labels["pod-security.kubernetes.io/enforce"] == "restricted"

    assert len(deployments) == 5
    assert (
        len({item["spec"]["template"]["spec"]["serviceAccountName"] for item in deployments}) == 5
    )
    for deployment in deployments:
        pod_spec = deployment["spec"]["template"]["spec"]
        container = pod_spec["containers"][0]
        assert pod_spec["securityContext"]["runAsNonRoot"] is True
        assert pod_spec["securityContext"]["seccompProfile"]["type"] == "RuntimeDefault"
        assert container["securityContext"]["allowPrivilegeEscalation"] is False
        assert container["securityContext"]["readOnlyRootFilesystem"] is True
        assert container["securityContext"]["capabilities"]["drop"] == ["ALL"]
        assert container["resources"]["requests"]
        assert container["resources"]["limits"]
        assert container["readinessProbe"] and container["livenessProbe"]


def test_workload_image_runs_as_non_root_standard_package() -> None:
    dockerfile = Path("examples/reference_workload/Dockerfile").read_text(encoding="utf-8")
    assert "USER 10001:10001" in dockerfile
    assert "PYTHONDONTWRITEBYTECODE=1" in dockerfile
    assert "reference_workload.main:app" in dockerfile


def test_ci_workflow_runs_quality_build_and_evaluation() -> None:
    workflow = yaml.safe_load(Path(".github/workflows/ci.yml").read_text(encoding="utf-8"))
    steps = workflow["jobs"]["quality"]["steps"]
    commands = {step["run"] for step in steps if "run" in step}
    assert {"make quality", "make build", "make evaluate-summary"} <= commands


def test_local_markdown_links_resolve() -> None:
    link_pattern = re.compile(r"\[[^]]+\]\(([^)]+)\)")
    markdown_files = [Path("README.md")]
    markdown_files.extend(sorted(Path("docs").glob("*.md")))

    broken: list[str] = []
    for document in markdown_files:
        for target in link_pattern.findall(document.read_text(encoding="utf-8")):
            path_text = target.split("#", 1)[0]
            if not path_text or "://" in path_text or path_text.startswith("mailto:"):
                continue
            resolved = (document.parent / path_text).resolve()
            if not resolved.exists():
                broken.append(f"{document}: {target}")
    assert broken == []
