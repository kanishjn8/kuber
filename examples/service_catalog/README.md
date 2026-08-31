# Reference service catalog

Each directory is an independently routed service boundary. The small source
files describe owner-intended Kubernetes behavior; the live kind sandbox uses the
instrumented runtime in `examples/reference_workload` to execute those calls
against real Kubernetes without duplicating HTTP and client plumbing five times.

`service-context.yaml` is metadata for reproducible local discovery. Kubernetes
discovery uses matching `kuber.dev/*` Deployment annotations, so the Kuber engine
does not contain a hard-coded service list.
