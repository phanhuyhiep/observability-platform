#!/bin/bash
# patch-otel-endpoint.sh
# Patch microservices-demo deployments to send traces to OTel Collector
# in the observability namespace.
#
# Google microservices-demo uses:
#   COLLECTOR_SERVICE_ADDR  (gRPC endpoint, no http:// prefix)
#   OTEL_SERVICE_NAME       (service identity)
#   ENABLE_TRACING          (must be "1" to activate)

set -euo pipefail

OTEL_ENDPOINT="otel-collector-opentelemetry-collector.observability.svc.cluster.local:4317"
NAMESPACE="${1:-default}"

echo "==> Patching microservices-demo in namespace: ${NAMESPACE}"
echo "==> OTel Collector endpoint: ${OTEL_ENDPOINT}"
echo ""

# Services that support tracing in microservices-demo
declare -A SERVICES=(
  ["checkoutservice"]="checkoutservice"
  ["currencyservice"]="currencyservice"
  ["emailservice"]="emailservice"
  ["frontend"]="frontend"
  ["paymentservice"]="paymentservice"
  ["productcatalogservice"]="productcatalogservice"
  ["recommendationservice"]="recommendationservice"
)

for DEPLOY in "${!SERVICES[@]}"; do
  SVC_NAME="${SERVICES[$DEPLOY]}"
  echo "Patching ${DEPLOY}..."
  kubectl set env deployment/${DEPLOY} \
    -n "${NAMESPACE}" \
    COLLECTOR_SERVICE_ADDR="${OTEL_ENDPOINT}" \
    OTEL_SERVICE_NAME="${SVC_NAME}" \
    ENABLE_TRACING="1" \
    2>/dev/null && echo "  ✓ ${DEPLOY} patched" || echo "  ✗ ${DEPLOY} not found, skipping"
done

echo ""
echo "==> Done! Pods will restart with tracing enabled."
echo "==> Verify with: kubectl get pods -n ${NAMESPACE} -w"
echo ""
echo "Note: adservice and shippingservice do not support COLLECTOR_SERVICE_ADDR in this demo version."
