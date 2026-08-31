# Improvement Changelog

This document explains how Kuber changed during development and what we learned from each step.

## Summary

The project started with a very simple idea:

> Keep only the Kubernetes permissions that appear in runtime observations.

That produced small policies, but it broke valid rare workflows.

The biggest improvement was adding a **verify → diagnose → repair → retry** loop.

## Changelog

| Stage | What we tried | What happened | Decision |
|---|---|---|---|
| **Baseline: observed-only** | Keep only permissions seen in normal runtime activity. | The policies became very small, but only **4 of 14** evaluation scenarios still worked. | Kept only as the comparison baseline. |
| **Deterministic RBAC engine** | Parse and reason about RBAC using normal code instead of asking an LLM to make security decisions. | Policy decisions became reproducible and testable. | Kept. |
| **Verification loop** | After creating a smaller policy, run the workload owner's tests before accepting it. | Rare paths that were missing from runtime observation became visible. | Kept. |
| **Targeted repair** | When Kubernetes/test verification reports a missing permission, restore only that originally allowed capability and retry. | Kuber reached **14/14** functional success in the evaluation. | Kept. This was the most important improvement. |
| **LangGraph workflow** | Represent inspect → propose → validate → apply → verify → diagnose → repair as explicit graph states. | Retries and decisions became easier to inspect and record. | Kept. |
| **Removed experiment: whole-repository context** | Let each workload analysis repeatedly read a large repository. | Too much irrelevant context was loaded again and again. | Removed as the normal approach. Replaced with service-scoped context. |
| **Service-scoped context** | Index each service once and give workers only the relevant service files/context. | The recorded experiment reduced inspected context from 980 files / 1,781,680 bytes to 10 files / 3,294 bytes. | Kept. |
| **Kafka worker execution** | Turn each service optimization into an independent task consumed by workers. | Services can progress independently and the architecture can scale horizontally. | Kept, without claiming linear scaling. |
| **Redis coordination** | Add fast coordination for locks/deduplication. | Helps prevent two workers from changing the same workload at the same time. | Kept. |
| **Optional Gemini explanations** | Use an LLM to turn technical failures into readable explanations. | Helpful for diagnosis text, but unnecessary for authorization truth. | Kept as optional only. |

## Biggest improvement

The biggest improvement was **verification plus targeted repair**.

Before it, the system could make a policy look very small while silently removing permissions needed by rare workflows.

After it, Kuber could:

```text
try smaller policy
      ↓
run tests
      ↓
find missing permission
      ↓
restore only that permission
      ↓
retry
```

That changed the evaluation from:

```text
Observed-only baseline:
4 / 14 scenarios worked
```

to:

```text
Kuber:
14 / 14 scenarios worked
```

## Removed experiment

### Whole-repository context loading

An early direction was to let workload analysis repeatedly inspect the entire repository.

This does not scale well for large systems because most files are unrelated to the service being optimized.

Kuber now builds service-scoped context.

A payment worker receives payment context. An order worker receives order context.

Extra dependency context is loaded only when needed.

## Main failure mode

The most important failure we found was:

> **What a service used during normal observation is not always everything the service needs.**

Rare workflows may not appear in the observation window.

That is why observation alone cannot safely prove least privilege.

## Main contribution

Kuber turns RBAC reduction into a feedback loop:

```text
observe
→ reduce
→ apply
→ verify
→ learn from failure
→ repair
→ verify again
```

## Hot take

> **Runtime observation gives least-observed privilege, not necessarily least-required privilege.**

For least privilege to be useful, the smaller policy must also be proven against real workload behavior.
