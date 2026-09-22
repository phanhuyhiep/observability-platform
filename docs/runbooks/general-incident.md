# SRE Runbook: General Microservices Incident Response

**Scope:** Áp dụng cho mọi sự cố đa dịch vụ hoặc chưa xác định rõ nguyên nhân ban đầu trên nền tảng Observability.  
**Level:** L1 / L2 On-Call SRE Engineer  

---

## 1. Nguyên Tắc Xử Lý Sự Cố (SRE Golden Rules)

1. **Khôi phục dịch vụ trước (Mitigate First), Phân tích chuyên sâu sau (Debug Later):** Mục tiêu số 1 là giảm MTTR (Mean Time To Recovery) để bảo vệ người dùng.
2. **Không hành động mù quáng:** Luôn kiểm tra trạng thái Pod và Trace trước khi can thiệp cấu hình.
3. **Cập nhật trạng thái sự cố liên tục:** Chuyển trạng thái sự cố từ `OPEN` ➔ `ACKNOWLEDGED` ➔ `INVESTIGATING` ➔ `RESOLVED`.

---

## 2. Quy Trình Điều Tra Chuẩn 4 Bước

### Bước 1: Kiểm tra tài nguyên Cluster & Node
```bash
# Kiểm tra CPU & Memory trên các Kubernetes Nodes
kubectl top nodes

# Kiểm tra các Pod tiêu tốn tài nguyên cao nhất
kubectl top pods -A --sort-by=cpu | head -n 15
```

### Bước 2: Kiểm tra các Pod bị lỗi hoặc khởi động lại gần đây
```bash
# Tìm các pod không ở trạng thái Running / Ready
kubectl get pods -A --field-selector=status.phase!=Running

# Tìm các pod bị restart nhiều lần
kubectl get pods -A --sort-by='.status.containerStatuses[0].restartCount' | tail -n 15
```

### Bước 3: Soi Trace phân tán trên Grafana Tempo
- Mở Grafana: [http://172.16.20.26:4000](http://172.16.20.26:4000)
- Vào Explore ➔ Chọn Tempo ➔ Tra cứu trace ID hoặc lọc theo mã lỗi `status=error`.

### Bước 4: Xem AI Incident Copilot & Đề Xuất Runbook
Mở báo cáo điều tra AI của sự cố:
- Executive Summary: `http://172.16.20.26:30083/api/v1/incidents/<INCIDENT_ID>/summary`
- Runbook & Investigation: `http://172.16.20.26:30083/api/v1/incidents/<INCIDENT_ID>/recommendations`

---

## 3. Quản Lý Vòng Đời Sự Cố qua SRE Operations CLI

```bash
# 1. Xác nhận tiếp nhận sự cố (ACK)
python3 scripts/sre_ops.py --ack <INCIDENT_ID> --actor "sre-oncall"

# 2. Bắt đầu điều tra (Investigate)
python3 scripts/sre_ops.py --investigate <INCIDENT_ID> --actor "sre-oncall"

# 3. Đánh dấu đã khắc phục (Resolve) kèm ghi chú
python3 scripts/sre_ops.py --resolve <INCIDENT_ID> --actor "sre-oncall" --comment "Đã scale phục hồi pod và dịch vụ đã ổn định"

# 4. Đóng hồ sơ sự cố (Close)
python3 scripts/sre_ops.py --close <INCIDENT_ID> --actor "sre-lead"
```
