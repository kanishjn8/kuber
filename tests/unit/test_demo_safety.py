from pathlib import Path

import pytest

from demo_layer.adapter.kubernetes_environment import DryRunOnlyError, KubernetesEnvironment
from rules_engine.models import Permission, Policy


def test_unrecognized_environment_defaults_to_dry_run(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(KubernetesEnvironment, "_is_recognized_sandbox", lambda self: False)
    environment = KubernetesEnvironment(artifact_directory=tmp_path)
    assert environment.dry_run
    candidate = Policy(
        (Permission("", "pods", "list", "kuber-demo"),),
        name="candidate",
        service_account="payment-controller",
        service_account_namespace="kuber-demo",
    )
    with pytest.raises(DryRunOnlyError):
        environment.apply_policy(candidate)
    assert (tmp_path / "payment-controller.yaml").exists()

