#!/usr/bin/env bash
set -euo pipefail

kubectl --context kind-kuber delete role payment-controller-kuber-kuber-demo -n kuber-demo --ignore-not-found
kubectl --context kind-kuber delete rolebinding payment-controller-kuber-kuber-demo-binding -n kuber-demo --ignore-not-found
kubectl --context kind-kuber apply -f demo_layer/kubernetes/overprivileged-rbac.yaml
kubectl --context kind-kuber -n kuber-demo rollout restart deployment/payment-controller
kubectl --context kind-kuber -n kuber-demo rollout status deployment/payment-controller --timeout=120s
echo "Demo restored to the intentionally overprivileged policy."

