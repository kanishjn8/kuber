from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ServiceAccountRef:
    name: str
    namespace: str


@dataclass(frozen=True, slots=True)
class WorkloadRef:
    name: str
    namespace: str
    service_account: ServiceAccountRef

