#!/usr/bin/env bash
set -euo pipefail

for service_id in api-gateway auth-service order-service payment-service worker-service; do
  ./deploy/kind/scripts/service-smoke.sh "$service_id"
done
echo "KUBER_SYSTEM_SUMMARY=5/5"
