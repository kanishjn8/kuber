#!/usr/bin/env bash
set -euo pipefail

for service_id in api-gateway auth-service order-service payment-service worker-service; do
  case "$service_id" in
    api-gateway) port=18101 ;;
    auth-service) port=18102 ;;
    order-service) port=18103 ;;
    payment-service) port=18104 ;;
    worker-service) port=18105 ;;
  esac
  log_file="/tmp/kuber-${service_id}-warmup.log"
  kubectl --context kind-kuber -n kuber-sandbox port-forward "service/${service_id}" "${port}:8080" >"$log_file" 2>&1 &
  forward_pid=$!
  ready=false
  for _ in {1..50}; do
    if curl -fsS "http://127.0.0.1:${port}/healthz" >/dev/null 2>&1; then
      ready=true
      break
    fi
    sleep 0.2
  done
  if [[ "$ready" == "false" ]]; then
    kill "$forward_pid" >/dev/null 2>&1 || true
    echo "Warmup port-forward failed for ${service_id}" >&2
    sed -n '1,80p' "$log_file" >&2
    exit 1
  fi
  curl -fsS "http://127.0.0.1:${port}/profile" >/dev/null
  kill "$forward_pid" >/dev/null 2>&1 || true
  wait "$forward_pid" 2>/dev/null || true
  echo "KUBER_WARMUP ${service_id}=PASS"
done
echo "Warmup complete; worker-service rare Job reconciliation was intentionally not exercised."
