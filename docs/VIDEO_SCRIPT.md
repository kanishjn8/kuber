# Solution video script

Maximum length: five minutes. Keep the terminal readable and use one prepared
reference-sandbox run; do not wait for cluster creation on camera.

## 0:00–0:35 — Problem and intended user

- Show the README title and one excessive Role.
- Explain that platform and security engineers want narrower Kubernetes RBAC,
  but normal traffic rarely covers every legitimate controller path.
- State the principle: **LLM proposes; Rules Engine validates; Environment proves.**

## 0:35–1:00 — Simple baseline

- Show `artifacts/evaluation/report.md`.
- Explain that observed-only reduction removes 97.5% of permissions but passes
  only 4/14 cases, so its validated risk reduction is only 27.4%.
- Emphasize that a smaller broken policy is not least privilege.

## 1:00–3:20 — Real end-to-end execution

- Start from a prepared cluster: `make sandbox-status`.
- Run `GEMINI_API_KEY= make sandbox-run` so no cluster diagnostic leaves the machine.
- Narrate discovery of five annotated workloads and service-scoped indexing.
- Point out five Kafka tasks distributed to asynchronous workers.
- Follow `worker-service` through the per-workload LangGraph.
- Show the observed candidate omitting the rare Job workflow.
- Pause on the **real Kubernetes 403** for Job `create`.
- Explain that deterministic validation confirms the denied capability existed
  in the original policy; optional LLM text is explanation only.
- Show `REPAIR_POLICY → APPLY_POLICY → VERIFY` for `create`, `get`, and `delete`.
- End on 3/3 worker tests, 5/5 workload results, and final system PASS.

## 3:20–4:05 — Final comparison

- Return to the generated comparison: baseline 4/14 versus Kuber 14/14;
  27.4% versus 91.9% VRR; 97.5% versus 95.3% raw reduction.
- Mention 19 repair iterations across the complete benchmark.
- State that human time and cost per task were not measured.

## 4:05–4:40 — Improvement changelog

- Show `docs/IMPROVEMENT_CHANGELOG.md`.
- Name verification plus targeted repair as the largest contribution.
- Explain that explicit graph transitions made failures and retries auditable.

## 4:40–4:55 — Rejected experiment

- Show the context-routing evidence: whole-repository loading was measured and
  rejected as the normal strategy in favor of service-owned paths.
- Mention that a linear Kafka scaling claim was also rejected because the
  recorded experiment has only two single-trial points.

## 4:55–5:00 — Close

“Runtime observation finds least-observed privilege. Verification is what turns
it into evidence for least-required privilege.”

## Recording checklist

- Keep the final video at or below 5:00.
- Use the latest generated evaluation artifacts; do not type metrics manually.
- Show the real 403, repair transition, retry, and PASS clearly.
- Keep API keys, kubeconfig content, and `.env` off-screen.
- Replace the README video placeholder with the uploaded URL.
