# Improvement changelog

All figures below are from the 2026-08-29 local deterministic evaluation; the
generated report remains the source of truth.

| Stage | Change | Result/observation | Decision |
|---|---|---|---|
| Baseline | Narrow policy to observed events only | 3/10 cases preserved behavior; average VRR 28.8% | Retained as comparison |
| Iteration 1 | Deterministic risk and wildcard/scope reduction | Candidates were narrower, but observation missed rare paths | Retained |
| Iteration 2 | Apply and owner-defined verification loop | Hidden paths became visible as denied events | Retained |
| Iteration 3 | Restore only originally granted denied capabilities | Kuber reached 10/10 with 7 repair iterations and 91.3% average VRR | Retained |
| Iteration 4 | Optional LLM explanation with deterministic fallback | Not enabled; no measured improvement claimed | Kept optional, excluded from score |

The live Docker/kind path was written but not executed in this code-only pass,
so no live-cluster success result is claimed here.

