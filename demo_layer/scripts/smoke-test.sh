#!/usr/bin/env bash
set -euo pipefail

kubectl --context kind-kuber -n kuber-demo port-forward service/payment-controller 18080:8080 >/tmp/kuber-port-forward.log 2>&1 &
forward_pid=$!
cleanup() { kill "$forward_pid" >/dev/null 2>&1 || true; }
failure() {
  echo "Smoke test failed; recent workload logs:" >&2
  kubectl --context kind-kuber -n kuber-demo logs deployment/payment-controller --tail=100 >&2 || true
}
trap cleanup EXIT
trap failure ERR
for _ in {1..30}; do
  curl -fsS http://127.0.0.1:18080/healthz >/dev/null && break
  sleep 0.2
done
curl -fsS http://127.0.0.1:18080/healthz >/dev/null
curl -fsS http://127.0.0.1:18080/config >/dev/null
curl -fsS http://127.0.0.1:18080/secret >/dev/null
curl -fsS http://127.0.0.1:18080/pods >/dev/null
curl -fsS -X POST http://127.0.0.1:18080/reconcile/kuber-smoke >/dev/null
curl -fsS -X POST http://127.0.0.1:18080/leader-election >/dev/null
echo "6/6 smoke behaviors passed."

