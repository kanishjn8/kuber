from rules_engine.minimizer import observed_only_policy
from rules_engine.models import KubeEvent, Policy


class ReducerAgent:
    def propose(self, current: Policy, observed: tuple[KubeEvent, ...]) -> Policy:
        return observed_only_policy(current, observed)

