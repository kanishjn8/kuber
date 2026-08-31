# Reference Kubernetes workload

This FastAPI service makes real in-cluster Kubernetes client calls. Every call
emits Kuber's normalized event JSON before execution, and a second structured
record on a 403. `/leader-election` is a legitimate low-frequency path omitted
from warmup and included in the full smoke test.
