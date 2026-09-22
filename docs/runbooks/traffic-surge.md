# SRE Runbook: Traffic Surge & Load Shedding

**Service:** `loadgenerator` / Ingress Gateways  
**Namespace:** `default`  
**Tier:** Traffic Injection / Ingress Traffic  
**Downstream Impact:** `frontend`, `productcatalogservice`, `cartservice`, `adservice`  

---

## 1. Overview & Mechanics

Khi lưu lượng truy cập tăng vọt đột biến (Traffic Surge) gấp 4–10 lần ngưỡng baseline thông thường:
- Các worker thread trên `frontend` bị bão hòa (Thread Pool Exhaustion).
- Tỷ lệ CPU đạt 100%, dẫn tới hiện tượng CPU Throttling trên Kubernetes.
- Hàng đợi request trên các dịch vụ hạ lưu bị ứ đọng, gây tăng vọt Latency p95/p99 và lỗi HTTP 504 Gateway Timeout.

---

## 2. Triệu Chứng Nhận Biết

| Tín hiệu | Ngưỡng cảnh báo | Nhận diện hệ thống |
|---|---|---|
| **Request Throughput** | Tăng > 300% so với baseline EWMA | Anomaly Detector cảnh báo Traffic Surge |
| **p95 Latency** | Tăng từ 40ms lên > 1500ms | EWMA & Z-Score đồng loạt nổ cảnh báo vàng/đỏ |
| **HTTP 5xx Rate** | > 5% tổng request | Khách hàng gặp màn hình chờ hoặc lỗi tải trang |

---

## 3. Quy Trình Điều Tra & Đánh Giá

### Bước 1: Kiểm tra số lượng replica của loadgenerator
```bash
kubectl get deployment loadgenerator -n default -o jsonpath='{.spec.replicas}'
```
*Đánh giá:* Nếu replicas > 1, có thể hệ thống đang chịu đợt stress test hoặc tăng tải nhân tạo.

### Bước 2: Kiểm tra mức tiêu thụ CPU/RAM của các Pod trong cluster
```bash
kubectl top pods -n default --sort-by=cpu
```

### Bước 3: Quan sát biểu đồ Request Rate và Latency trên Grafana
- Mở Grafana Dashboard: [http://172.16.20.26:4000](http://172.16.20.26:4000)
- Kiểm tra bảng **Live Traffic & Anomaly Detection**.

---

## 4. Biện Pháp Xử Lý (Mitigation & Load Shedding)

### Xử lý 1: Hạ tải khẩn cấp loadgenerator về 1 replica
```bash
kubectl scale deployment/loadgenerator --replicas=1 -n default
```

### Xử lý 2: Scale up tạm thời Frontend để chống đỡ lưu lượng
Nếu đây là lưu lượng khách hàng thực tế (flash sale, chiến dịch marketing):
```bash
kubectl scale deployment/frontend --replicas=3 -n default
kubectl scale deployment/productcatalogservice --replicas=3 -n default
```

---

## 5. Xác Nhận Sau Khắc Phục

1. Số lượng replica loadgenerator đã trở về 1:
   ```bash
   kubectl get pods -l app=loadgenerator -n default
   ```
2. Độ trễ p95 hạ về dưới 100ms trên Grafana.
3. Đóng sự cố:
   ```bash
   python3 scripts/sre_ops.py --resolve <INCIDENT_ID>
   ```
