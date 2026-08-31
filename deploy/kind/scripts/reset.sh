#!/usr/bin/env bash
set -euo pipefail

context=kind-kuber
namespace=kuber-sandbox
for service_id in api-gateway auth-service order-service payment-service worker-service; do
  service_account="${service_id}-sa"
  kubectl --context "$context" delete role "${service_account}-kuber-kuber-sandbox" \
    -n "$namespace" --ignore-not-found
  kubectl --context "$context" delete rolebinding "${service_account}-kuber-kuber-sandbox-binding" \
    -n "$namespace" --ignore-not-found
  kubectl --context "$context" -n "$namespace" rollout restart "deployment/${service_id}"
done
kubectl --context "$context" delete job kuber-worker-smoke -n "$namespace" --ignore-not-found
kubectl --context "$context" apply -f deploy/kind/reference-rbac.yaml
for service_id in api-gateway auth-service order-service payment-service worker-service; do
  kubectl --context "$context" -n "$namespace" rollout status \
    "deployment/${service_id}" --timeout=180s
done
echo "All reference workloads were restored to their intentionally excessive starting policies."
