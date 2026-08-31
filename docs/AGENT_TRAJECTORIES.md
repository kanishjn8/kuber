# Agent Trajectories

Kuber records what happened during each workflow so that a reviewer can follow the agent's decisions.

The goal is not just to show the final policy.

The trajectory should answer:

> What did Kuber see, what did it try, what happened, and why did it choose the next step?

## Workload workflow

A typical service follows:

```text
LOAD CONTEXT
      ↓
INSPECT RBAC
      ↓
GATHER EVIDENCE
      ↓
PROPOSE SMALLER POLICY
      ↓
VALIDATE
      ↓
APPLY
      ↓
VERIFY
   ↙       ↘
 PASS      FAIL
  ↓          ↓
FINALIZE   DIAGNOSE
              ↓
            REPAIR
              ↓
             RETRY
```

## Example: worker-service

A useful representative trajectory is the hidden Job workflow.

### 1. Load service context

Kuber loads only the worker service's context:

```text
service: worker-service
source path: worker-service files
service account: worker-sa
verification profile: worker smoke tests
```

### 2. Inspect current access

The deterministic RBAC engine resolves the permissions currently available to the service.

### 3. Gather evidence

Normal warmup shows only the Kubernetes operations that were exercised.

The rare Job workflow is intentionally not triggered yet.

### 4. Propose a smaller policy

Kuber creates a narrow candidate based on the evidence it has.

The candidate is still considered **unverified**.

### 5. Apply and verify

Kuber applies the candidate in the reference sandbox and runs the owner-defined verification profile.

The rare reconciliation path now executes.

Kubernetes returns:

```text
403: cannot create batch/jobs
```

### 6. Diagnose

The workflow identifies:

```text
missing capability:
jobs:create
```

Optional Gemini text may explain this failure in plain language, but the authorization evidence comes from Kubernetes.

### 7. Repair

Kuber restores only:

```text
jobs:create
```

and retries.

The next run reaches:

```text
403: cannot get batch/jobs
```

Kuber restores only:

```text
jobs:get
```

and retries.

The next run reaches:

```text
403: cannot delete batch/jobs
```

Kuber restores only:

```text
jobs:delete
```

and retries.

### 8. Final verification

The service passes all three tests.

Kuber accepts the verified policy.

## Why this trajectory matters

This example shows the key difference between Kuber and an observed-only reducer.

The observed-only approach would stop after making the small policy.

Kuber keeps interacting with the environment until the candidate is either verified or rejected.

## Stored trajectory format

Every run writes:

```text
JSONL machine trajectory
+
readable Markdown summary
```

Records include fields such as:

```json
{
  "agent": "verifier",
  "action": "verify",
  "decision": "diagnose",
  "retry_count": 1
}
```

and structured details such as denied Kubernetes capabilities.

Artifacts are stored under:

```text
artifacts/trajectories/
```

## What judges should look for

Representative trajectories should show:

- the input/context,
- the policy Kuber proposed,
- tools/environment calls,
- verification feedback,
- conditional decisions,
- retries,
- repairs,
- final acceptance or failure.

Trajectories make the workflow auditable, but they do not replace actual verification.
