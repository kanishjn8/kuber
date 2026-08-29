# Security model

Kuber treats model output, logs, benchmark files, and generated YAML as
untrusted inputs. Security-sensitive decisions are deterministic:

- parser rejects unsupported kinds, verbs, resources, and malformed rules;
- authorization accounts for groups, resources, verbs, namespace, wildcards,
  and conservative `resourceNames` behavior;
- observed and repaired calls must have been allowed by the original policy;
- generated live YAML is parsed/resolved and compared with the candidate;
- functional success comes only from the environment;
- loops have a fixed repair limit;
- non-sandbox Kubernetes contexts default to dry-run.

`resourceNames` is applied only to get/update/patch/delete in this normalized
model. List/watch would require an exact field selector not represented by
`KubeEvent`, and create cannot be safely name-constrained by RBAC.

The demo Secret contains only a fake value. Kuber does not store kubeconfig,
tokens, or real Secret contents, and optional LLM context contains only a short
failure summary and normalized denied events. Gemini credentials are loaded
from the ignored `.env` file or process environment and are never placed in
prompts, reports, or trajectories.
