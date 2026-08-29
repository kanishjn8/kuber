You are a senior software architect, Kubernetes security engineer, Python engineer, and agentic-systems engineer.

I want you to build a hackathon project named:

Kuber

Tagline:
"An agentic least-privilege compiler for Kubernetes workloads."

Do not immediately start writing random code. First understand the architecture, create a short implementation plan, then implement it incrementally while continuously running tests.

============================================================
1. PROJECT PURPOSE
============================================================

Kuber solves a specific Kubernetes RBAC problem:

Organizations frequently give Kubernetes workloads more permissions than they need because removing permissions risks breaking the workload.

Kuber should:

1. Inspect the RBAC currently granted to a Kubernetes ServiceAccount.
2. Determine its effective permissions.
3. Observe which Kubernetes API capabilities the workload actually uses.
4. Generate a smaller candidate RBAC policy.
5. Apply that candidate inside a controlled environment.
6. Run developer-provided functional verification tests.
7. Detect when removing a permission breaks legitimate behavior.
8. Restore/refine only the required permission.
9. Continue tightening the policy where possible.
10. Produce:
   - a minimized RBAC policy,
   - before/after privilege metrics,
   - a risk report,
   - verification results,
   - an agent trajectory,
   - a human-readable explanation.

The core optimization problem is:

MINIMIZE:
    privilege(policy)

SUBJECT TO:
    verification_tests(policy) == PASS

The key principle is:

The LLM may PROPOSE and EXPLAIN.
The environment must PROVE.

Never trust an LLM to determine whether an RBAC policy is valid or whether a workload functions correctly.

============================================================
2. CRITICAL ARCHITECTURAL REQUIREMENT
============================================================

There are TWO execution environments but ONE Kuber engine.

A. Judge Layer
   - deterministic
   - simulated
   - no Kubernetes installation required
   - no Docker required if avoidable
   - no external LLM API required
   - designed for clean-environment reproducibility

B. Demo Layer
   - actual Docker
   - actual kind Kubernetes cluster
   - actual Kubernetes RBAC enforcement
   - actual ServiceAccount
   - actual workload making Kubernetes API calls
   - actual functional tests

The SAME:

- rules engine
- agent layer
- orchestration
- permission representation
- policy minimization logic
- reporting system

must be used by both.

Only the EnvironmentAdapter implementation changes.

Judge:
    SimulatorEnvironment

Demo:
    KubernetesEnvironment

Do NOT create separate implementations of Kuber for the judge and demo.

============================================================
3. REPOSITORY STRUCTURE
============================================================

Use ONE Git repository.

Repository name:

kuber/

Use this high-level structure:

kuber/
│
├── rules_engine/
│
├── agent_layer/
│
├── judge_layer/
│
├── demo_layer/
│
├── workload_src/
│
├── docs/
│
├── artifacts/
│
├── tests/
│
├── README.md
├── Makefile
├── pyproject.toml
├── .env.example
├── .gitignore
└── LICENSE

Do NOT split this into multiple repositories.

============================================================
4. DEPENDENCY DIRECTION
============================================================

The architectural dependency direction must be:

rules_engine
     ↑
agent_layer
   ↑     ↑
judge   demo

Conceptually:

rules_engine
    <- agent_layer
        <- judge_layer
        <- demo_layer

The rules engine must NOT depend on:

- Kubernetes Python client
- Docker
- kind
- judge simulator
- demo implementation
- any LLM API

The agent layer must NOT directly implement Kubernetes-specific behavior.

It communicates with environments through an interface.

============================================================
5. RULES ENGINE
============================================================

Folder:

rules_engine/

This is deterministic security logic.

Suggested structure:

rules_engine/
├── __init__.py
├── models/
│   ├── __init__.py
│   ├── permission.py
│   ├── policy.py
│   ├── workload.py
│   └── event.py
│
├── rbac/
│   ├── __init__.py
│   ├── parser.py
│   ├── resolver.py
│   ├── authorization.py
│   ├── canonicalizer.py
│   └── generator.py
│
├── minimizer/
│   ├── __init__.py
│   ├── candidates.py
│   ├── strategies.py
│   └── reducer.py
│
└── risk/
    ├── __init__.py
    ├── rules.py
    └── scorer.py

Use a canonical permission representation similar to:

Permission(
    api_group="",
    resource="secrets",
    verb="get",
    namespace="payments",
    resource_name="stripe-key"
)

Also define a normalized Kubernetes event representation:

KubeEvent(
    api_group="",
    resource="configmaps",
    verb="get",
    namespace="payments",
    resource_name="app-config"
)

The rules engine must support parsing:

- ServiceAccount
- Role
- ClusterRole
- RoleBinding
- ClusterRoleBinding

It must resolve effective permissions for a ServiceAccount.

MVP API support:

Core API:
- pods
- configmaps
- secrets
- services

apps/v1:
- deployments

batch/v1:
- jobs

coordination.k8s.io:
- leases

MVP verbs:

- get
- list
- watch
- create
- update
- patch
- delete

Architect the code so additional resources can be added later.

Do NOT attempt full Kubernetes authorization semantics in the hackathon MVP.

Explicitly document unsupported cases.

Potential future features include:

- CRDs
- non-resource URLs
- admission control
- cloud IAM
- aggregated ClusterRoles
- impersonation
- service mesh authorization
- custom authorization webhooks

============================================================
6. RBAC AUTHORIZATION ENGINE
============================================================

Implement deterministic authorization logic that can answer:

Would policy P authorize event E?

Example:

Event:
    verb=get
    resource=secrets
    namespace=payments
    resource_name=stripe-key

Result:
    ALLOWED or DENIED

Correctly account for:

- apiGroups
- resources
- verbs
- namespaces
- resourceNames
- wildcard "*"

Be careful with Kubernetes resourceNames behavior.

Do not incorrectly apply resourceNames-based optimization to list/watch requests unless the request semantics actually allow it.

Unit test this extensively.

============================================================
7. RISK ENGINE
============================================================

Do not only report:

"40 permissions became 8."

Implement an explainable heuristic Privilege Risk Score.

The score is NOT an industry security standard.

Clearly document that it is a benchmark/project heuristic.

Risk signals can include:

- wildcard verbs
- wildcard resources
- cluster-wide scope
- ClusterRoleBinding
- access to Secrets
- mutating verbs
- delete permissions
- role/RBAC modification capabilities if supported
- overly broad namespace scope

The scoring must be deterministic and documented.

Output explanations such as:

Current risk:
91

Reasons:
+ wildcard verbs
+ cluster-wide scope
+ list secrets
+ create deployments

Candidate risk:
14

Risk reduction:
84.6%

Also report raw permission reduction independently.

============================================================
8. POLICY MINIMIZATION
============================================================

The rules engine should provide deterministic candidate reductions.

Potential strategies:

1. Remove completely unused resources.
2. Remove unused verbs.
3. Replace wildcard verbs.
4. Replace wildcard resources.
5. Reduce ClusterRole/ClusterRoleBinding to namespace-scoped Role/RoleBinding where possible.
6. Restrict get access to specific resourceNames where valid.
7. Order candidate removals using risk score.

Do not let the LLM directly emit arbitrary security policies without validation.

Every generated candidate must pass through the deterministic parser and authorization engine.

============================================================
9. AGENT LAYER
============================================================

Folder:

agent_layer/

Suggested structure:

agent_layer/
├── __init__.py
├── interfaces/
│   └── environment.py
│
├── inspector.py
├── reducer.py
├── verifier.py
├── orchestrator.py
│
├── llm/
│   ├── provider.py
│   ├── failure_reasoner.py
│   └── prompts/
│
└── trajectory/
    ├── recorder.py
    └── models.py

Use only THREE logical agent roles:

Inspector Agent
Reducer Agent
Verifier Agent

Do not add agents unless clearly necessary.

------------------------------------------------------------
Inspector Agent
------------------------------------------------------------

Responsibilities:

- obtain current RBAC from EnvironmentAdapter
- resolve effective permissions using rules_engine
- obtain normalized observed Kubernetes usage
- identify unused/broad privileges
- calculate current risk
- produce inspection result

------------------------------------------------------------
Reducer Agent
------------------------------------------------------------

Responsibilities:

- obtain deterministic candidate reductions from rules_engine
- prioritize high-value reductions
- propose candidate policy
- never directly assume the candidate is safe

------------------------------------------------------------
Verifier Agent
------------------------------------------------------------

Responsibilities:

- apply candidate through EnvironmentAdapter
- run verification
- inspect failures
- detect authorization denials
- determine which permission was incorrectly removed
- restore/refine minimal capability
- rerun tests
- only accept a reduction after verification passes

------------------------------------------------------------
Orchestrator
------------------------------------------------------------

The orchestrator runs:

INSPECT
    ↓
PROPOSE
    ↓
APPLY
    ↓
VERIFY
    ↓
if fail:
    DIAGNOSE
    REPAIR
    RETRY
    ↓
if pass:
    KEEP REDUCTION
    TRY FURTHER TIGHTENING
    ↓
FINAL VERIFY
    ↓
REPORT

Set sensible iteration limits so loops cannot run forever.

============================================================
10. ENVIRONMENT INTERFACE
============================================================

Create an EnvironmentAdapter Protocol/ABC.

Conceptual API:

class EnvironmentAdapter:
    def get_current_policy(...)
    def get_observed_usage(...)
    def apply_policy(...)
    def verify_workload(...)
    def restore_policy(...)
    def describe_failure(...)

Both environments must implement it:

judge_layer.simulator.SimulatorEnvironment

demo_layer.adapter.KubernetesEnvironment

The Kuber orchestrator must not care which one it receives.

============================================================
11. LLM USAGE
============================================================

Do NOT make Kuber dependent on heavy LLM usage.

Most logic must remain deterministic.

LLM usage should primarily help with:

- interpreting unusual failure logs
- explaining why a permission may be required
- suggesting a repair when deterministic mapping is insufficient
- producing human-readable reasoning

A representative case:

stderr:

"failed to initialize leader election:
leases.coordination.k8s.io is forbidden"

LLM can hypothesize:

"Leader election likely requires get/create/update access to leases."

But:

- rules engine validates the generated permission
- environment applies it
- verification proves whether it works

Implement an LLMProvider abstraction.

The system must remain runnable WITHOUT an API key.

When no LLM is configured:

- deterministic failure reasoning should be used
- evaluation must still run
- no crash

If an LLM API is configured, it may enhance reasoning.

Do not send entire repositories to an LLM.

Send only relevant structured context.

============================================================
12. AGENT TRAJECTORIES
============================================================

Every Kuber run must generate machine-readable trajectories.

Example:

artifacts/trajectories/<run-id>.jsonl

Each step should include things like:

- timestamp
- run id
- environment
- agent
- current policy summary
- proposed action
- reason
- tool/action performed
- verification result
- failure
- decision
- retry count

Example:

{
  "agent": "reducer",
  "action": "remove_permission",
  "permission": "secrets:list",
  "reason": "not observed and high-risk"
}

followed by:

{
  "agent": "verifier",
  "verification": "PASS",
  "tests_passed": 12,
  "tests_total": 12,
  "decision": "keep_removal"
}

Generate readable trajectory summaries too.

============================================================
13. JUDGE LAYER
============================================================

Folder:

judge_layer/

Purpose:

Allow a judge to evaluate the project's main result from a clean environment without installing Kubernetes.

Suggested structure:

judge_layer/
├── __init__.py
├── simulator/
│   ├── environment.py
│   ├── authorization.py
│   └── workload_runner.py
│
├── baseline/
│   └── observed_only.py
│
├── benchmarks/
│   ├── 01_config_reader/
│   ├── 02_secret_reader/
│   ├── 03_job_controller/
│   ├── 04_leader_election/
│   ├── 05_namespace_scope/
│   ├── 06_resource_name/
│   ├── 07_hidden_path/
│   ├── 08_wildcard_verbs/
│   ├── 09_cluster_scope/
│   └── 10_mixed_workload/
│
├── evaluation/
│   ├── runner.py
│   ├── metrics.py
│   ├── compare.py
│   └── report.py
│
└── README.md

The simulator is NOT a Kubernetes simulator.

It only simulates the RBAC authorization behavior Kuber needs.

It should consume normalized KubeEvents and determine whether candidate RBAC would ALLOW/DENY them.

============================================================
14. BENCHMARK FORMAT
============================================================

Each benchmark should contain data such as:

initial-rbac.yaml
observed-events.json
verification-tests.yaml
expected-minimum.yaml
metadata.yaml

Important:

observed-events.json must NOT always contain every legitimate capability.

verification-tests.yaml should contain some valid behaviors that were not present in observed traffic.

This demonstrates the key problem:

"Observed privilege" is not necessarily "required privilege."

Example:

Observed:
    get configmaps/app-config

Hidden legitimate path:
    list configmaps

Naive observed-only reducer:
    removes list

Verification:
    FAIL

Kuber:
    detects the 403
    restores list
    reruns
    PASS

At least one benchmark must intentionally be challenging.

============================================================
15. PRIMARY BASELINE
============================================================

Implement a deterministic baseline:

Observed-Only Reducer

Algorithm:

1. Read observed Kubernetes API events.
2. Generate the narrowest policy that allows exactly those observed calls.
3. Do not perform verification.
4. Return the policy.

This is intentionally reasonable but incomplete.

Use the exact same benchmark cases for:

- baseline
- Kuber

Do not give Kuber easier cases.

An optional one-shot LLM baseline may be included later, but it must NOT be required.

============================================================
16. EVALUATION METRICS
============================================================

Define ONE primary metric:

Validated Risk Reduction (VRR)

Suggested definition:

If all functional verification tests pass:
    VRR = percentage reduction in risk score

If verification fails:
    VRR = 0 for that benchmark

This rewards both:

- security reduction
- functional correctness

Also report secondary metrics:

- functional workload success rate
- average raw permission reduction
- average risk reduction
- high-risk permissions remaining
- cluster-wide grants remaining
- number of incorrect removals
- number of repair iterations
- average runtime per case
- number of benchmark cases

Produce:

artifacts/evaluation/results.json
artifacts/evaluation/results.csv
artifacts/evaluation/report.md

Never fabricate evaluation results.

All README numbers must be generated from real evaluation output.

============================================================
17. JUDGE COMMANDS
============================================================

The final project should support:

uv sync
make test
make evaluate

The ideal judge workflow is:

git clone <repository>
cd kuber
uv sync
make evaluate

No Kubernetes.
No kind.
No Docker if avoidable.
No cloud account.
No kubeconfig.
No LLM API key.

`make evaluate` should:

1. run all benchmark cases
2. run baseline
3. run Kuber
4. compare them
5. calculate metrics
6. generate artifacts
7. print a concise final table

Example presentation:

Kuber Evaluation
================================================

Cases                         10

                         Baseline      Kuber
Functional success         7/10        10/10
Validated Risk Reduction    43%          86%
Raw privilege reduction     67%          89%
Cluster-wide grants left      5            0

Do not hardcode numbers.

============================================================
18. DEMO WORKLOAD SOURCE
============================================================

Folder:

workload_src/

This contains the source code of the ACTUAL application deployed into Kubernetes.

Use one primary demo application:

workload_src/payment_controller/

Suggested structure:

workload_src/
└── payment_controller/
    ├── src/
    │   ├── main.py
    │   ├── tracked_kube_client.py
    │   └── services/
    │
    ├── tests/
    ├── Dockerfile
    ├── pyproject.toml
    └── README.md

Use Python + FastAPI unless there is a strong reason not to.

The application must actually use the Kubernetes Python client from inside the cluster using its ServiceAccount.

Capabilities should include a useful subset such as:

- read ConfigMap app-config
- read Secret payment-secret
- list Pods in its namespace
- create/get/delete reconciliation Jobs

Add one legitimate less-common path that is not exercised during initial observation but IS exercised by the full smoke tests.

This allows the live demonstration to show:

observed-only candidate
    ↓
permission missing
    ↓
real Kubernetes 403
    ↓
Verifier diagnoses
    ↓
permission restored/refined
    ↓
smoke tests pass

============================================================
19. TRACKED KUBERNETES CLIENT
============================================================

Do NOT build a generic Kubernetes audit-log parser in the MVP.

Inside the demo workload, wrap Kubernetes API calls with a small tracked client.

Before/around each real Kubernetes API call, emit a normalized structured event.

Example:

{
  "kuber_event": true,
  "api_group": "",
  "resource": "configmaps",
  "verb": "get",
  "namespace": "payments",
  "resource_name": "app-config"
}

The actual Kubernetes API call must still be real.

Observation is instrumented.
Authorization is real.

The demo adapter can retrieve structured events from workload logs.

Keep the normalized event representation identical to the judge simulator.

============================================================
20. DEMO LAYER
============================================================

Folder:

demo_layer/

Suggested structure:

demo_layer/
├── __init__.py
│
├── adapter/
│   └── kubernetes_environment.py
│
├── observation/
│   └── event_collector.py
│
├── cluster/
│   └── kind-config.yaml
│
├── kubernetes/
│   ├── namespace.yaml
│   ├── service-account.yaml
│   ├── configmap.yaml
│   ├── secret.yaml
│   ├── deployment.yaml
│   ├── service.yaml
│   └── overprivileged-rbac.yaml
│
└── scripts/
    ├── check-prerequisites.sh
    ├── setup.sh
    ├── smoke-test.sh
    ├── reset.sh
    └── cleanup.sh

The demo uses:

Docker
    ↓
kind
    ↓
real Kubernetes cluster
    ↓
real workload
    ↓
real ServiceAccount
    ↓
real RBAC
    ↓
real Kubernetes API authorization

Cluster name:

kind-kuber

Namespace:

kuber-demo

============================================================
21. INITIAL DEMO RBAC
============================================================

The demo workload must start intentionally overprivileged.

For example it may initially have broad access to:

- pods
- secrets
- configmaps
- services
- deployments
- jobs

with excessive verbs.

Potentially start with cluster-scoped access so Kuber can demonstrate scope reduction.

But do not make the demo so unrealistic that it looks fabricated solely for the benchmark.

Document why such broad policies commonly arise from:

- quick development setups
- copied example manifests
- temporary debugging privileges
- broad controller roles

============================================================
22. REAL DEMO WORKFLOW
============================================================

Support commands similar to:

make demo-check
make demo-up
make demo
make demo-down

`make demo-check`:
- verify Docker
- verify kind
- verify kubectl
- print actionable error messages

`make demo-up`:
- build demo workload Docker image
- create kind-kuber
- load image into kind
- deploy namespace
- deploy ServiceAccount
- deploy intentionally excessive RBAC
- deploy ConfigMap
- deploy fake Secret
- deploy application
- wait for Ready

`make demo`:
- show current RBAC/risk
- warm up workload and collect observed events
- run initial smoke test
- execute Kuber
- apply candidates
- observe real Kubernetes failures where applicable
- repair policy
- rerun smoke tests
- generate final policy
- print before/after report

`make demo-down`:
- remove kind-kuber cleanly

Prefer an additional:

make demo-reset

for quickly returning to the intentionally overprivileged starting state.

============================================================
23. DEMO SMOKE TESTS
============================================================

Kuber must NOT try to invent how arbitrary applications are tested.

The workload owner provides a verification command.

Conceptually:

verification:
    command: "./demo_layer/scripts/smoke-test.sh"
    timeout: 90

The smoke tests should check actual application behavior.

Examples:

- health endpoint succeeds
- ConfigMap reading succeeds
- Secret reading succeeds
- Pod listing succeeds
- reconciliation workflow succeeds
- Job creation succeeds
- Job completion/status succeeds

The smoke tests are the user's definition of healthy.

============================================================
24. KUBERNETES ENVIRONMENT ADAPTER
============================================================

Implement:

demo_layer.adapter.KubernetesEnvironment

It must use the same EnvironmentAdapter interface as the simulator.

Responsibilities:

- read current manifests/RBAC
- collect normalized observed events
- apply candidate RBAC
- restart/refresh workload if required
- wait for readiness
- execute smoke-test command
- capture stdout/stderr
- detect Kubernetes 403 authorization errors
- restore previous policy
- return structured verification results

Use subprocess wrappers carefully.

Return structured typed results instead of passing raw shell text throughout the system.

============================================================
25. SAFETY REQUIREMENTS
============================================================

This is extremely important.

Kuber must never casually modify an arbitrary Kubernetes cluster.

Live mutation should only be automatically allowed when the cluster is clearly the sandbox.

For example:

current context / cluster must match:
    kind-kuber

and/or namespace must contain:
    kuber.dev/sandbox=true

Outside a recognized sandbox:

DEFAULT TO DRY RUN.

Generate the proposed patch but require explicit human approval.

Never commit real secrets.

Demo Secret must contain fake values.

Do not store kubeconfig or credentials in the repository.

============================================================
26. REPORTING
============================================================

Generate a polished final report.

Example:

KUBER ANALYSIS
================================================

Workload:
payment-controller

ServiceAccount:
payment-controller

Current Policy
------------------------------------------------
Effective permissions:       43
Cluster-wide grants:          8
Privilege risk score:        91

High-risk findings:
- wildcard verbs
- cluster-wide Secret access
- unnecessary deployment mutation
- unnecessary Pod deletion

Observed Usage
------------------------------------------------
get configmaps/app-config
get secrets/payment-secret
list pods
create jobs

Candidate #1
------------------------------------------------
Risk score: 16

Verification:
11/12 PASS

Failure:
list configmaps forbidden

Repair:
restored configmaps:list

Candidate #2
------------------------------------------------
Verification:
12/12 PASS

Further tightening:
Secret read limited to payment-secret

Final
------------------------------------------------
Effective permissions:       43 -> 6
Risk score:                   91 -> 12
Cluster-wide grants:           8 -> 0
Verification:              12/12 PASS

Output:
artifacts/policies/payment-controller.yaml

Again:
Do not hardcode these numbers.

============================================================
27. DOCUMENTATION
============================================================

Documentation is a first-class deliverable.

Create:

docs/
├── ARCHITECTURE.md
├── JUDGE_GUIDE.md
├── DEMO_GUIDE.md
├── REPRODUCTION.md
├── EVALUATION.md
├── SECURITY_MODEL.md
├── DESIGN_DECISIONS.md
├── LIMITATIONS.md
├── IMPROVEMENT_CHANGELOG.md
├── AGENT_TRAJECTORIES.md
├── HOT_TAKE.md
└── VIDEO_SCRIPT.md

------------------------------------------------------------
README.md
------------------------------------------------------------

The root README should quickly answer:

1. What problem does Kuber solve?
2. Who experiences this problem?
3. Why existing observation/static analysis is insufficient?
4. What does Kuber do differently?
5. Architecture diagram.
6. Judge quickstart.
7. Live demo quickstart.
8. Evaluation summary.
9. Safety boundaries.
10. Limitations.

At the top include:

Want to evaluate Kuber?
→ docs/JUDGE_GUIDE.md

Want to run the real Kubernetes demo?
→ docs/DEMO_GUIDE.md

Want to understand the system?
→ docs/ARCHITECTURE.md

============================================================
28. REPRODUCTION GUIDE
============================================================

REPRODUCTION.md must assume a clean environment.

Document:

- operating systems tested
- Python version
- uv version
- exact commands
- expected runtime
- whether internet is required
- external API requirements
- approximate LLM cost if LLM mode is used
- expected outputs
- how to reproduce evaluation results

Judge evaluation must not require Kubernetes.

Demo requirements should be documented separately.

============================================================
29. IMPROVEMENT CHANGELOG
============================================================

Track the actual development/evaluation progression.

Suggested experimental progression:

Baseline:
Observed-only policy generation

Iteration 1:
Add risk-aware deterministic candidate reduction

Iteration 2:
Add functional verification loop

Iteration 3:
Add failure diagnosis and repair

Iteration 4:
Add optional LLM failure reasoner if it measurably helps

Final:
Combine only improvements proven useful

For every stage record:

- what changed
- why
- evaluation result
- what failed
- decision: kept / revised / removed

DO NOT fabricate historical results.

Populate this from actual evaluation runs.

============================================================
30. HOT TAKE / CORE INSIGHT
============================================================

Evaluate whether the following insight is supported by results:

"Runtime observation alone does not produce least privilege.
It produces least observed privilege.
Verification is what turns observation into a safer least-privilege workflow."

Do not state this as proven unless evaluation supports it.

Use failures to refine the insight.

============================================================
31. TESTING
============================================================

Write extensive tests.

tests/
├── unit/
│   ├── test_rbac_parser.py
│   ├── test_resolver.py
│   ├── test_authorization.py
│   ├── test_risk.py
│   ├── test_policy_generator.py
│   └── test_reduction.py
│
└── integration/
    ├── test_simulator_agent_loop.py
    └── test_reports.py

Test especially:

- wildcard permissions
- namespace boundaries
- RoleBinding behavior
- ClusterRoleBinding behavior
- resourceNames
- missing verbs
- hidden verification path
- restore after failed reduction
- invalid YAML
- unsupported resource behavior

Run tests continuously during implementation.

============================================================
32. IMPLEMENTATION ORDER
============================================================

Follow this order.

PHASE 0
- establish repository
- create architecture documentation
- define models/interfaces
- create Makefile
- configure Python/uv
- establish tests

PHASE 1
- permission model
- event model
- RBAC parser
- effective-permission resolver
- authorization evaluator

PHASE 2
- risk engine
- deterministic candidate generator
- policy YAML generator

PHASE 3
- judge simulator
- 3 initial benchmark cases
- observed-only baseline
- evaluation metrics

PHASE 4
- Inspector
- Reducer
- Verifier
- orchestrator
- verification/retry loop
- trajectory recorder

PHASE 5
- grow benchmark suite to >=10 cases
- run baseline vs Kuber
- fix correctness bugs
- produce evaluation artifacts

PHASE 6
- build payment-controller source
- Dockerfile
- tracked Kubernetes client
- smoke tests

PHASE 7
- kind demo cluster
- Kubernetes manifests
- KubernetesEnvironment adapter
- real RBAC apply/revert
- end-to-end live demo

PHASE 8
- optional LLM reasoner
- use only if it improves hard-case handling
- compare before vs after
- remove it if it does not improve the system

PHASE 9
- documentation
- improvement changelog
- trajectory examples
- video script
- polish CLI/output
- reproduction testing

Do NOT start with the LLM.

============================================================
33. CODE QUALITY
============================================================

Requirements:

- Python 3.12
- uv for dependency management
- full type hints
- dataclasses or Pydantic where appropriate
- pytest
- small cohesive modules
- no giant god classes
- no hidden global state
- deterministic benchmark execution
- useful exceptions
- structured logs
- clear interfaces
- docstrings for security-sensitive logic

A lightweight CLI library such as Typer may be used.

Do not introduce unnecessary frameworks.

============================================================
34. CLI
============================================================

Create a CLI executable:

kuber

Useful commands may include:

kuber inspect ...
kuber minimize ...
kuber evaluate ...
kuber report ...
kuber demo ...

Do not overbuild the CLI.

Makefile remains the primary reproduction interface.

============================================================
35. IMPORTANT SCOPE LIMITATIONS
============================================================

Do NOT attempt:

- generic Kubernetes audit-log ingestion
- arbitrary application test generation
- arbitrary production-cluster mutation
- complete Kubernetes RBAC semantics
- CRD inference
- cloud IAM minimization
- service mesh policies
- admission control
- multi-cluster orchestration
- automatic production deployment

These are Future Work.

The hackathon goal is a polished, reliable proof of the core workflow.

============================================================
36. DEFINITION OF DONE
============================================================

The project is not done until ALL of these work:

1.

uv sync

2.

make test

passes.

3.

make evaluate

runs from a clean Python environment without Kubernetes or an LLM key.

4.

At least 10 benchmark scenarios exist.

5.

Baseline and Kuber run against identical cases.

6.

Evaluation artifacts are generated from real runs.

7.

Agent trajectories are automatically recorded.

8.

No evaluation numbers are hardcoded.

9.

The real payment-controller runs in kind.

10.

The workload uses a real Kubernetes ServiceAccount.

11.

The workload makes real Kubernetes API requests.

12.

Kubernetes itself enforces RBAC.

13.

Kuber can apply a reduced policy in kind.

14.

Removing a required permission causes a real 403/failing test.

15.

The verifier repairs/refines the candidate.

16.

Final smoke tests pass.

17.

The final RBAC is meaningfully narrower than the initial policy.

18.

make demo-up
make demo
make demo-down

work and are documented.

19.

A clean reproduction guide exists.

20.

Architecture, limitations, safety model, changelog, evaluation methodology and trajectories are documented.

============================================================
37. DEVELOPMENT BEHAVIOR
============================================================

While implementing:

- work phase-by-phase
- do not silently skip requirements
- run tests after meaningful changes
- keep a TODO/checklist
- record architectural decisions
- do not fabricate benchmark success
- do not modify tests just to make incorrect logic pass
- prefer deterministic behavior over LLM calls
- do not expand scope without justification
- report blockers clearly
- preserve clean module boundaries

Before implementing each major phase, state:

1. what you are about to build
2. files that will change
3. why this phase exists

After the phase:

1. run relevant tests
2. report results
3. explain remaining limitations
4. continue only when the current layer is stable

============================================================
38. FINAL PRODUCT STORY
============================================================

The finished demonstration should communicate this story clearly:

A Kubernetes workload starts with excessive RBAC.

A simplistic observed-only reducer removes everything it did not see.

That policy looks secure but breaks a legitimate less-common workflow.

Kuber instead:

observes
→ minimizes
→ applies
→ verifies
→ sees the real failure
→ diagnoses the missing permission
→ repairs only that capability
→ continues tightening
→ reruns all tests
→ produces a verified least-privilege candidate

The final result is not:

"AI generated some YAML."

The final result is:

"Kuber experimentally demonstrated that a substantially smaller RBAC policy still preserves the workload's declared functionality."

Build toward that exact outcome.