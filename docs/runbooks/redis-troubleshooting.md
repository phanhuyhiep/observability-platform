# SRE Runbook: Redis Crash & Cache Unavailability Recovery

**Service:** `redis-cart`  
**Namespace:** `default`  
**Tier:** In-Memory Database / Cache Layer  
**Role:** Lưu trữ session và danh sách items giỏ hàng của từng User  
**Port:** `6379/TCP`  
**Upstream Callers:** `cartservice`  

---

## 1. Overview & Failure Mechanics

`redis-cart` là leaf dependency trọng yếu (được xếp hạng cao nhất trong thuật toán Random Walk Root Cause Analysis).
Khi Redis gặp sự cố (bị crash, OOM, scale về 0 hoặc nghẽn IO):
- Toàn bộ kết nối từ `cartservice` bị ngắt hoặc dính Connection Timeout.
- Không thể đọc/ghi dữ liệu giỏ hàng.
- Lỗi lan truyền theo chuỗi Domino: `redis-cart` ➔ `cartservice` ➔ `frontend` & `checkoutservice`.

---

## 2. Triệu Chứng & Cảnh Báo

| Chỉ số | Ngưỡng bất thường | Ý nghĩa |
|---|---|---|
| **Pod Status** | `CrashLoopBackOff` / `OOMKilled` / `0 replicas` | Database ngừng phục vụ hoàn toàn |
| **TCP Connection** | Connection Refused trên port 6379 | Socket bị ngắt hoặc process terminated |
| **RCA Score** | Root Cause Confidence > 90% | RCA Engine định vị `redis-cart` là gốc rễ sự cố |

---

## 3. Quy Trình Điều Tra Chi Tiết

### Bước 1: Kiểm tra trạng thái Pod và Replicas
```bash
kubectl get deployment redis-cart -n default
kubectl get pods -l app=redis-cart -n default
```
*Đánh giá:*
- Nếu Replicas = 0: Có thể ai đó đã vô tình scale hạ dịch vụ hoặc bị can thiệp bởi Chaos Simulator.
- Nếu Pod bị `OOMKilled`: Redis đã sử dụng vượt quá `resources.limits.memory`.

### Bước 2: Kiểm tra lý do Pod bị Terminate
```bash
kubectl describe pod -l app=redis-cart -n default | grep -E "State|Reason|Exit Code|Last State"
```

### Bước 3: Soi log của Redis
```bash
kubectl logs -l app=redis-cart --tail=50
```

### Bước 4: Kiểm tra kết nối mạng từ CartService sang Redis
```bash
kubectl exec deployment/cartservice -- nc -zv redis-cart 6379
```

---

## 4. Biện Pháp Xử Lý Khẩn Cấp (Emergency Remediation)

### Xử lý 1: Khôi phục Replicas về 1 nếu pod bị scale 0
```bash
kubectl scale deployment/redis-cart --replicas=1 -n default
```

### Xử lý 2: Khởi động lại Pod nếu Redis bị deadlock hoặc tràn RAM
```bash
kubectl rollout restart deployment/redis-cart -n default
```

### Xử lý 3: Cấu hình tăng giới hạn Memory Limit (nếu OOMKilled)
```bash
kubectl set resources deployment/redis-cart -c redis --limits=memory=512Mi,cpu=500m -n default
```

---

## 5. Xác Nhận Sau Khắc Phục

1. Kiểm tra Pod `redis-cart` đã `1/1 Running`:
   ```bash
   kubectl get pods -l app=redis-cart -n default
   ```
2. Thử set/get một key kiểm tra:
   ```bash
   kubectl exec deployment/redis-cart -- redis-cli ping
   # Kết quả mong đợi: PONG
   ```
3. Đóng sự cố:
   ```bash
   python3 scripts/sre_ops.py --resolve <INCIDENT_ID>
   ```
