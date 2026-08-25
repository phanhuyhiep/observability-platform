# Phase 1 – Deploy Guide

Hướng dẫn deploy Observability Stack trên Minikube đang chạy microservices-demo.

## Prerequisites

```bash
# 1. Cài Helm (nếu chưa có)
sudo snap install helm --classic

# Verify
helm version
```

## Deploy (chạy lần lượt)

```bash
# 0. CD vào thư mục infrastructure/
cd ~/k8s-lab/infrastructure

# 1. Tạo namespace
kubectl create namespace observability

# 2. Thêm Helm repos
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo add grafana https://grafana.github.io/helm-charts
helm repo add open-telemetry https://open-telemetry.github.io/opentelemetry-helm-charts
helm repo update

# 3. Deploy Prometheus
helm install prometheus prometheus-community/kube-prometheus-stack \
  -n observability \
  -f metrics/prometheus-values.yaml

# 4. Deploy Loki
helm install loki grafana/loki \
  -n observability \
  -f logging/loki-values.yaml

# 5. Deploy Promtail
helm install promtail grafana/promtail \
  -n observability \
  -f logging/promtail-values.yaml

# 6. Deploy Tempo
helm install tempo grafana/tempo \
  -n observability \
  -f tracing/tempo-values.yaml

# 7. Deploy OTel Collector
helm install otel-collector open-telemetry/opentelemetry-collector \
  -n observability \
  -f tracing/otel-collector-values.yaml

# 8. Deploy Grafana
helm install grafana grafana/grafana \
  -n observability \
  -f grafana/grafana-values.yaml

# 9. Patch microservices-demo → trỏ traces tới OTel Collector
chmod +x tracing/patch-otel-endpoint.sh
bash tracing/patch-otel-endpoint.sh default
```

## Verify

```bash
# Tất cả pods running
kubectl get pods -n observability

# Resource usage (cần metrics-server)
kubectl top pods -n observability

# Lấy Grafana URL (Minikube)
minikube service grafana -n observability --url
# Hoặc dùng port-forward:
kubectl port-forward svc/grafana 3000:80 -n observability
# → Mở http://localhost:3000

# Login: admin / observability2026
```

### Verify trong Grafana

1. **Metrics**: Explore → Prometheus → query `up` → xem tất cả targets
2. **Logs**: Explore → Loki → query `{namespace="default"}` → xem logs
3. **Traces**: Explore → Tempo → Search → xem traces từ microservices-demo

## Uninstall

```bash
helm uninstall grafana -n observability
helm uninstall otel-collector -n observability
helm uninstall tempo -n observability
helm uninstall promtail -n observability
helm uninstall loki -n observability
helm uninstall prometheus -n observability
kubectl delete namespace observability
```

## Troubleshooting

| Vấn đề | Kiểm tra |
|---|---|
| Pod Pending (resources) | Minikube cần đủ RAM: `minikube config set memory 8192` rồi restart |
| Pod CrashLoopBackOff | `kubectl logs <pod> -n observability` |
| PVC Pending | `kubectl get sc` – cần storage class default (Minikube có sẵn) |
| Prometheus không scrape | `kubectl logs prometheus-prometheus-kube-prometheus-prometheus-0 -n observability` |
| Loki không nhận logs | `kubectl logs <promtail-pod> -n observability` |
| Tempo không nhận traces | Kiểm tra OTel Collector logs: `kubectl logs <otel-pod> -n observability` |
| Grafana datasource lỗi | Kiểm tra DNS: `kubectl get svc -n observability` |
| Grafana NodePort ko access được | Dùng `kubectl port-forward svc/grafana 3000:80 -n observability` thay thế |
