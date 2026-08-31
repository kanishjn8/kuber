#!/usr/bin/env bash
set -euo pipefail

context=kind-kuber
namespace=kuber-sandbox
kubectl --context "$context" get deployments,pods,services -n "$namespace"
echo
kubectl --context "$context" get roles,rolebindings -n "$namespace"
echo
echo "Kafka topics:"
kubectl --context "$context" exec -n "$namespace" deployment/kafka -- \
  /opt/kafka/bin/kafka-topics.sh --bootstrap-server kafka:9092 --list
