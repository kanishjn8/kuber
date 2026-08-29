# Agent trajectories

Every orchestrator run writes JSON Lines and a readable Markdown summary. Each
record includes UTC timestamp, run/environment, logical agent, action, reason,
decision, retry count, and action-specific structured details.

```json
{"agent":"reducer","action":"propose_policy","reason":"narrowest supported policy for observed calls; verification still required"}
{"agent":"verifier","action":"verify","decision":"diagnose","details":{"denied_events":[{"resource":"configmaps","verb":"list"}]}}
{"agent":"verifier","action":"repair_policy","decision":"retry"}
{"agent":"orchestrator","action":"finalize","decision":"accept"}
```

Run identifiers are deterministic for evaluation and unique by default for
ad-hoc runs. Trajectories explain decisions but do not replace verification.

