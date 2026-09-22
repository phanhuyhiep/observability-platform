# SRE Runbook: Checkout & Payment Pipeline Troubleshooting

**Service:** `checkoutservice`  
**Namespace:** `default`  
**Tier:** Transactional Core / Order Processing  
**Upstream Callers:** `frontend`  
**Downstream Callers:** `cartservice`, `paymentservice`, `emailservice`, `shippingservice`, `currencyservice`, `productcatalogservice`  

---

## 1. Overview & Architecture

`checkoutservice` là dịch vụ giao thoa phức tạp nhất trong kiến trúc Online Boutique:
Nó thực hiện giao dịch phân tán (Distributed Transaction / Saga pattern):
1. Lấy thông tin giỏ hàng từ `cartservice`.
2. Lấy thông tin chi tiết từng sản phẩm từ `productcatalogservice`.
3. Chuyển đổi tiền tệ từ `currencyservice`.
4. Gọi `paymentservice` để trừ tiền thẻ tín dụng.
5. Gọi `shippingservice` để tạo tracking code vận chuyển.
6. Xóa giỏ hàng qua `cartservice`.
7. Gửi email xác nhận qua `emailservice`.

Nếu bất kỳ bước nào trong chuỗi bị timeout hoặc văng lỗi gRPC, toàn bộ đơn hàng sẽ thất bại.

---

## 2. Triệu Chứng Nhận Biết

| Triệu chứng | Nhận diện | Metric / Trace |
|---|---|---|
| **Payment Failed** | Khách hàng bấm "Place Order" báo lỗi thanh toán | `rpc error: code = Internal desc = failed to charge card` |
| **gRPC Timeout** | Đơn hàng treo trên 10 giây rồi timeout | gRPC Client Duration p99 > 5s |
| **Partial Failure** | Tiền bị trừ nhưng không tạo được đơn hàng | Kiểm tra trace phân tán trên Tempo |

---

## 3. Quy Trình Điều Tra Từng Bước

### Bước 1: Kiểm tra trạng thái Pods liên quan
```bash
kubectl get pods -l "app in (checkoutservice,paymentservice,emailservice,shippingservice)" -n default
```

### Bước 2: Kiểm tra nhật ký giao dịch thanh toán
```bash
kubectl logs -l app=checkoutservice --tail=100
kubectl logs -l app=paymentservice --tail=50
```

### Bước 3: Soi Trace phân tán trên Grafana Tempo
1. Mở Grafana: [http://172.16.20.26:4000](http://172.16.20.26:4000)
2. Explore ➔ **Tempo** ➔ Lọc Service: `checkoutservice`.
3. Xem Waterfall Span: Xác định span con nào (`Charge`, `ShipOrder`, `GetCart`) bị tô đỏ (Error code 13 hoặc DeadlineExceeded).

---

## 4. Biện Pháp Xử Lý Khẩn Cấp

### Xử lý 1: Khởi động lại Pod checkoutservice
```bash
kubectl rollout restart deployment/checkoutservice -n default
```

### Xử lý 2: Khởi động lại dịch vụ phụ thuộc gây lỗi (ví dụ paymentservice)
```bash
kubectl rollout restart deployment/paymentservice -n default
```

---

## 5. Xác Nhận Sau Khắc Phục

1. Đặt thử 1 đơn hàng test trên trang web: [http://172.16.20.26:8888](http://172.16.20.26:8888)
2. Kiểm tra màn hình xác nhận Order Confirmation thành công.
3. Đóng sự cố:
   ```bash
   python3 scripts/sre_ops.py --resolve <INCIDENT_ID>
   ```
