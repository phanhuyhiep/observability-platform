# SRE Runbook: Frontend Ingress & HTTP 500 Troubleshooting

**Service:** `frontend`  
**Namespace:** `default`  
**Tier:** Ingress / Web Presentation Layer (Go Template)  
**Port:** `8080/TCP` (Exposed as `8888` via port-forward)  
**Dependencies:** All backend microservices  

---

## 1. Overview & Mechanics

`frontend` là cổng giao tiếp trực tiếp với người dùng.
Mọi lỗi 500 xuất hiện trên giao diện người dùng đều được ghi nhận tại đây.
Lỗi HTTP 500 trên frontend thường chia làm 2 loại:
1. **Lỗi nội tại (Internal):** Lỗi render template Go, cạn kiệt socket hoặc crash container.
2. **Lỗi phụ thuộc (Upstream):** Các microservice backend (`cartservice`, `productcatalogservice`, v.v.) không phản hồi hoặc timeout.

---

## 2. Triệu Chứng Nhận Biết

| Triệu chứng | Nhận diện | Metric |
|---|---|---|
| **HTTP 5xx Rate Spike** | Tỷ lệ HTTP 500 vượt ngưỡng 2% | `http_requests_total{status=~"5.."}` |
| **Ingress Refused** | Trình duyệt báo `Connection Refused` trên cổng 8888 | Tiến trình port-forward bị ngắt |
| **CrashLoopBackOff** | Pod frontend khởi động lại liên tục | OOM hoặc Panic trong code Go |

---

## 3. Quy Trình Điều Tra Từng Bước

### Bước 1: Kiểm tra trạng thái Pods frontend
```bash
kubectl get pods -l app=frontend -n default
```

### Bước 2: Xem log lỗi HTTP 500 gần nhất
```bash
kubectl logs -l app=frontend --tail=100 | grep -E "500|Error|panic|rpc error"
```

### Bước 3: Thử kết nối nội bộ trong container
```bash
kubectl exec deployment/frontend -n default -- wget -qO- http://localhost:8080 > /dev/null && echo "Frontend OK"
```

---

## 4. Biện Pháp Khắc Phục

### Xử lý 1: Rolling restart frontend pods
```bash
kubectl rollout restart deployment/frontend -n default
```

### Xử lý 2: Kiểm tra và mở lại kết nối Port-Forward nếu truy cập bên ngoài bị mất
```bash
nohup kubectl port-forward svc/frontend 8888:80 --address 0.0.0.0 > /dev/null 2>&1 &
```

---

## 5. Xác Nhận Sau Khắc Phục

1. Truy cập lại trang chủ Online Boutique: [http://172.16.20.26:8888](http://172.16.20.26:8888)
2. Kiểm tra log không còn thông báo `HTTP 500`.
3. Đóng sự cố:
   ```bash
   python3 scripts/sre_ops.py --resolve <INCIDENT_ID>
   ```
