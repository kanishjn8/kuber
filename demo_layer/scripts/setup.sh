#!/usr/bin/env bash
set -euo pipefail

kind_name="kuber"
context="kind-kuber"
image="kuber-payment-controller:dev"

docker build -t "$image" workload_src/payment_controller
if ! kind get clusters | rg -x "$kind_name" >/dev/null 2>&1; then
  kind create cluster --name "$kind_name" --config demo_layer/cluster/kind-config.yaml
fi
kind load docker-image "$image" --name "$kind_name"
kubectl --context "$context" apply -f demo_layer/kubernetes/namespace.yaml
kubectl --context "$context" apply -f demo_layer/kubernetes/service-account.yaml
kubectl --context "$context" apply -f demo_layer/kubernetes/configmap.yaml
kubectl --context "$context" apply -f demo_layer/kubernetes/secret.yaml
kubectl --context "$context" apply -f demo_layer/kubernetes/overprivileged-rbac.yaml
kubectl --context "$context" apply -f demo_layer/kubernetes/service.yaml
kubectl --context "$context" apply -f demo_layer/kubernetes/deployment.yaml
kubectl --context "$context" -n kuber-demo rollout status deployment/payment-controller --timeout=120s
echo "kind-kuber is ready. Run: make demo"
