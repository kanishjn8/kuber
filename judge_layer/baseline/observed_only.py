from rules_engine.minimizer import observed_only_policy
from rules_engine.models import KubeEvent, Policy


def run_observed_only(current: Policy, observed: tuple[KubeEvent, ...]) -> Policy:
    """Primary baseline: minimize to observations and skip all verification."""

    return observed_only_policy(current, observed)

