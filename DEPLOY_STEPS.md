# Deploy Steps - Chạy trên server 172.16.20.26

```bash
cd ~/k8s-lab/detection

# 1. Fix database tables
kubectl exec -i deployment/detection-postgres -n observability -- psql -U detection -d detection_db -c "DROP TABLE IF EXISTS anomaly_events, baselines, detection_rules CASCADE;"
kubectl exec -i deployment/detection-postgres -n observability -- psql -U detection -d detection_db < migrations/001_create_anomaly_events.sql

# 2. Rebuild Docker image
eval $(minikube docker-env)
docker build -t detection-service:latest .

# 3. Restart detection service
kubectl rollout restart deployment/detection-service -n observability

# 4. Đợi pod ready
kubectl wait --for=condition=ready pod -l app=detection-service -n observability --timeout=60s

# 5. Port-forward lại
kubectl port-forward svc/detection-service 8080:8080 -n observability --address 0.0.0.0 &

# 6. Test
sleep 3
curl http://localhost:8080/api/v1/health
curl http://localhost:8080/api/v1/anomalies | python3 -m json.tool
```
