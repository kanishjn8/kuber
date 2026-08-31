#!/usr/bin/env bash
set -uo pipefail

service_id=${1:?usage: service-smoke.sh SERVICE_ID}
case "$service_id" in
  api-gateway) port=18101 ;;
  auth-service) port=18102 ;;
  order-service) port=18103 ;;
  payment-service) port=18104 ;;
  worker-service) port=18105 ;;
  *) echo "Unknown reference service: $service_id" >&2; exit 2 ;;
esac

log_file="/tmp/kuber-${service_id}-port-forward.log"
kubectl --context kind-kuber -n kuber-sandbox port-forward "service/${service_id}" "${port}:8080" >"$log_file" 2>&1 &
forward_pid=$!
cleanup() { kill "$forward_pid" >/dev/null 2>&1 || true; }
trap cleanup EXIT

ready=false
for _ in {1..50}; do
  if curl -fsS "http://127.0.0.1:${port}/healthz" >/dev/null 2>&1; then
    ready=true
    break
  fi
  sleep 0.2
done
if [[ "$ready" == "false" ]]; then
  echo "Port-forward for ${service_id} did not become ready:" >&2
  sed -n '1,120p' "$log_file" >&2
  exit 1
fi

passed=0
failed=0
run_test() {
  local test_name=$1
  shift
  if "$@" >/dev/null 2>&1; then
    echo "KUBER_TEST_RESULT ${test_name}=PASS"
    passed=$((passed + 1))
  else
    echo "KUBER_TEST_RESULT ${test_name}=FAIL"
    failed=1
  fi
}

run_test health curl -fsS "http://127.0.0.1:${port}/healthz"
run_test profile curl -fsS "http://127.0.0.1:${port}/profile"
total=2
if [[ "$service_id" == "worker-service" ]]; then
  run_test rare-job-reconciliation curl -fsS -X POST "http://127.0.0.1:${port}/rare-workflow"
  total=3
fi

echo "KUBER_TEST_SUMMARY=${passed}/${total}"
if [[ "$failed" -ne 0 ]]; then
  exit 1
fi
