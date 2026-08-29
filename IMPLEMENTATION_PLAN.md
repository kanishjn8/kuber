# Kuber implementation checklist

- [x] Phase 0: package structure, build configuration, core models, interfaces
- [x] Phase 1: RBAC parser, resolver, canonicalizer, authorization evaluator
- [x] Phase 2: deterministic risk and candidate policy generation
- [x] Phase 3: judge simulator, observed-only baseline, metrics
- [x] Phase 4: inspector/reducer/verifier orchestration and trajectories
- [x] Phase 5: ten shared benchmark cases and generated evaluation reports
- [x] Phase 6: instrumented payment-controller workload source
- [x] Phase 7: safe Kubernetes adapter, manifests, and kind scripts
- [x] Phase 8: optional LLM provider contract with deterministic fallback
- [x] Phase 9: CLI, documentation, tests, and reproduction workflow

Live Docker/kind execution is deliberately deferred. The implementation and
static/unit verification are included; `make demo-*` requires local tools.

