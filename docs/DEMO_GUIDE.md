# Live demo guide

Requirements: Docker with a running daemon, kind, kubectl, curl, Python 3.12,
and uv. The scripts create only cluster `kind-kuber`.

```bash
uv sync --extra demo
make demo-check
make demo-up
make demo
make demo-reset   # optional: restore broad RBAC for another run
make demo-down
```

`demo-up` builds the FastAPI payment controller, creates kind, loads the image,
and deploys fake configuration/credentials and intentionally broad RBAC.
`demo` exercises common paths as observation, proposes a candidate, then runs
six full behaviors including low-frequency leader election. Real 403 records
are emitted by the tracked client and used for bounded repair.

The smoke test is the workload owner's definition of health. Kuber does not
invent tests. If the current context or namespace label fails the sandbox
check, mutation is refused and only a proposal may be written.

