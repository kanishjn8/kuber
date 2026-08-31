#!/usr/bin/env bash
set -euo pipefail

kind_name="kuber"
context="kind-kuber"
image="kuber-reference-workload:dev"

docker build -t "$image" examples/reference_workload
cluster_exists=false
while IFS= read -r existing_cluster; do
  if [[ "$existing_cluster" == "$kind_name" ]]; then
    cluster_exists=true
    break
  fi
done < <(kind get clusters)
if [[ "$cluster_exists" == "false" ]]; then
  kind create cluster --name "$kind_name" --config deploy/kind/kind-config.yaml
fi
kind load docker-image "$image" --name "$kind_name"
kubectl --context "$context" apply -f deploy/kind/namespace.yaml
kubectl --context "$context" apply -f deploy/kind/infrastructure.yaml
kubectl --context "$context" -n kuber-sandbox rollout status deployment/kafka --timeout=180s
kubectl --context "$context" -n kuber-sandbox rollout status deployment/redis --timeout=120s
kubectl --context "$context" apply -f deploy/kind/configmap.yaml
kubectl --context "$context" apply -f deploy/kind/secret.yaml
kubectl --context "$context" apply -f deploy/kind/reference-rbac.yaml
kubectl --context "$context" apply -f deploy/kind/workloads.yaml
for deployment in api-gateway auth-service order-service payment-service worker-service; do
  kubectl --context "$context" -n kuber-sandbox rollout status "deployment/${deployment}" --timeout=180s
done
create_topic() {
  local topic="$1"
  local output
  if ! output="$(kubectl --context "$context" exec -n kuber-sandbox deployment/kafka -- \
    /opt/kafka/bin/kafka-topics.sh --bootstrap-server kafka:9092 --create --if-not-exists \
    --topic "$topic" --partitions 3 --replication-factor 1 2>&1)"; then
    printf '%s\n' "$output" >&2
    return 1
  fi
  while IFS= read -r line; do
    # Kafka warns for every dotted topic because dots and underscores map to
    # the same JMX metric name. Kuber consistently uses dots and no underscores,
    # so this known warning is noise; all other output and failures remain visible.
    if [[ "$line" != "WARNING: Due to limitations in metric names,"* ]]; then
      printf '%s\n' "$line"
    fi
  done <<<"$output"
}

for topic in \
  kuber.analysis.requests \
  kuber.workload.optimization.requests \
  kuber.workload.optimization.results \
  kuber.verification.events \
  kuber.system.events \
  kuber.dlq; do
  create_topic "$topic"
done
# Initialize Kafka's internal consumer-group metadata before the first visible
# sandbox run. The console consumer exits successfully after the bounded empty-topic
# timeout; suppress its expected timeout text while retaining command failures.
kubectl --context "$context" exec -n kuber-sandbox deployment/kafka -- \
  /opt/kafka/bin/kafka-console-consumer.sh --bootstrap-server kafka:9092 \
  --topic kuber.analysis.requests --group kuber-setup-readiness \
  --timeout-ms 1000 --max-messages 1 >/dev/null 2>&1
echo "kind-kuber, Kafka (KRaft), Redis, and five workloads are ready. Run: make sandbox-run"
