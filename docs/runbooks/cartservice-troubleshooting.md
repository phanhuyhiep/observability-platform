# SRE Runbook: CartService Troubleshooting & Rollout Recovery

**Service:** `cartservice`  
**Namespace:** `default`  
**Tier:** Critical In-Memory / gRPC Business Service  
**Architecture:** .NET 8 / gRPC Service backed by Redis  
**Upstream Callers:** `frontend`, `checkoutservice`  
**Downstream Dependencies:** `redis-cart:6379` (In-memory cart store)  

---

## 1. Overview & Business Impact

`cartservice` quản lý toàn bộ giỏ hàng của người dùng trên nền tảng Online Boutique:
- Thêm sản phẩm (`AddItemAsync`)
- Lấy giỏ hàng (`GetCartAsync`)
- Xóa giỏ hàng khi checkout (`EmptyCartAsync`)

Khi `cartservice` gặp sự cố:
- Người dùng bấm "Add to Cart" bị lỗi HTTP 500 trên `frontend`.
- Bước thanh toán (`checkoutservice`) không thể lấy giỏ hàng để tính tiền -> Tỷ lệ chuyển đổi đơn hàng giảm về 0% (**User Impact: CRITICAL**).

---

## 2. Triệu Chứng & Cảnh Báo Thường Gặp

| Triệu chứng | Dấu hiệu nhận biết | Metric / Log |
|---|---|---|
| **Rollout Failure / Misconfiguration** | Pod mới ở trạng thái `CrashLoopBackOff` hoặc `0/1 Running` | `REDIS_ADDR` sai host/port |
| **Connection Timeout** | `StackExchange.Redis.RedisConnectionException` | Tăng vọt latency p99 > 2s |
| **Upstream 500 Burst** | `frontend` log `rpc error: code = Unavailable` | HTTP 5xx error rate > 10% |

---

## 3. Quy Trình Điều Tra Từng Bước (Step-by-Step Investigation)

### Bước 1: Kiểm tra trạng thái Pods và sự kiện Rollout
```bash
kubectl get pods -l app=cartservice -n default
kubectl rollout status deployment/cartservice -n default
```
*Mục đích:* Xác định xem pod đang chạy ổn định hay đang bị kẹt trong chu kỳ khởi động lại.

### Bước 2: Kiểm tra cấu hình biến môi trường `REDIS_ADDR`
```bash
kubectl describe deployment/cartservice | grep -A 8 Environment
```
*Mục đích:* Kiểm tra xem kỹ sư DevOps có vô tình cấu hình sai địa chỉ Redis (ví dụ: `invalid-redis-host:6379` thay vì `redis-cart:6379`).

### Bước 3: Soi StackTrace lỗi trong log
```bash
# Xem 100 dòng log gần nhất
kubectl logs -l app=cartservice --tail=100

# Lọc riêng các Exception nghiêm trọng
kubectl logs -l app=cartservice --tail=100 | grep -E -i "Exception|Error|Timeout"
```

### Bước 4: Kiểm tra kết nối mạng TCP tới Redis
```bash
# Thử kết nối cổng 6379 từ chính container hoặc pod phụ trợ
kubectl exec deployment/cartservice -- nc -zv redis-cart 6379 || echo "TCP connect failed"
```

### Bước 5: Soi Trace phân tán trên Grafana Tempo
1. Mở Grafana: [http://172.16.20.26:4000](http://172.16.20.26:4000)
2. Điều hướng tới **Explore** -> Chọn Data source: **Tempo**.
3. Tìm kiếm theo Service: `cartservice` hoặc `frontend`.
4. Tìm các trace có `status=error` hoặc `duration > 1s`.

---

## 4. Biện Pháp Khắc Phục (Remediation & Recovery)

### Kịch bản A: Rollout thất bại do sai cấu hình biến môi trường
Nếu phát hiện `REDIS_ADDR` sai, thực hiện sửa ngay:
```bash
# Cách 1: Rollback về phiên bản trước (khuyến nghị cho production)
kubectl rollout undo deployment/cartservice -n default

# Cách 2: Cập nhật lại đúng địa chỉ redis-cart:6379
kubectl set env deployment/cartservice REDIS_ADDR=redis-cart:6379 -n default
```

### Kịch bản B: Pod bị treo thread pool hoặc socket connection leak
Nếu pod vẫn Ready nhưng xử lý chậm chạp hoặc log đầy warning:
```bash
kubectl rollout restart deployment/cartservice -n default
```

### Kịch bản C: Do Redis hạ lưu (`redis-cart`) bị sập
Nếu `cartservice` không lỗi cấu hình nhưng Redis bị crash:
```bash
kubectl scale deployment/redis-cart --replicas=1 -n default
```

---

## 5. Xác Nhận Sau Khắc Phục (Verification Checklist)

- [ ] Tất cả Pod `cartservice` đạt trạng thái `1/1 Running`:
  ```bash
  kubectl get pods -l app=cartservice -w
  ```
- [ ] Không còn log `RedisConnectionException`:
  ```bash
  kubectl logs -l app=cartservice --tail=30
  ```
- [ ] Kiểm tra tính năng thêm giỏ hàng trên giao diện: [http://172.16.20.26:8888](http://172.16.20.26:8888)
- [ ] Đóng sự cố trên hệ thống SRE CLI:
  ```bash
  python3 scripts/sre_ops.py --resolve <INCIDENT_ID>
  ```
