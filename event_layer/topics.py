from enum import StrEnum


class Topic(StrEnum):
    ANALYSIS_REQUESTS = "kuber.analysis.requests"
    OPTIMIZATION_REQUESTS = "kuber.workload.optimization.requests"
    OPTIMIZATION_RESULTS = "kuber.workload.optimization.results"
    VERIFICATION_EVENTS = "kuber.verification.events"
    SYSTEM_EVENTS = "kuber.system.events"
    DLQ = "kuber.dlq"


OPTIMIZATION_CONSUMER_GROUP = "kuber-optimization-workers"
