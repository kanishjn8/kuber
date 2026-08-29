# Design decisions

1. **Atomic permissions.** Each group/resource/verb/scope/name combination is
   explicit, making matching and repair reviewable.
2. **Environment proof.** Observation proposes; owner-defined verification
   accepts. There is no LLM safety oracle.
3. **Conservative names.** Named RBAC applies only where normalized request
   semantics are sufficient.
4. **One simulator purpose.** The judge models only authorization needed by the
   project, avoiding a misleading partial Kubernetes implementation.
5. **No required LLM SDK.** Optional Gemini explanation uses its REST API behind
   a provider protocol and falls back to deterministic text on any failure.
6. **Generated artifacts.** Reports and trajectories come from each run.
