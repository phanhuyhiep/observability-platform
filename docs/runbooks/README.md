# SRE Incident Investigation Runbooks

Tập hợp tài liệu hướng dẫn vận hành chuẩn (Standard Operating Procedures - SOPs & Runbooks) cho kỹ sư SRE và DevOps khi xử lý các sự cố microservice được phát hiện bởi hệ thống Observability Platform & AI Incident Copilot.

---

## 📚 Danh Mục Runbooks Theo Dịch Vụ

| Dịch vụ | Tài liệu Runbook | Mô tả sự cố thường gặp |
|---|---|---|
| **cartservice** | [CartService Troubleshooting](file:///e:/observability-platform/docs/runbooks/cartservice-troubleshooting.md) | Rollout thất bại, sai cấu hình `REDIS_ADDR`, socket leak |
| **redis-cart** | [Redis Crash & Cache Unavailability](file:///e:/observability-platform/docs/runbooks/redis-troubleshooting.md) | Sập database đệm, OOMKilled, scale về 0 |
| **loadgenerator** | [Traffic Surge & Load Shedding](file:///e:/observability-platform/docs/runbooks/traffic-surge.md) | Tăng tải đột biến, nghẽn luồng xử lý CPU/RAM |
| **checkoutservice** | [Checkout & Payment Pipeline](file:///e:/observability-platform/docs/runbooks/checkout-troubleshooting.md) | Lỗi thanh toán, deadlock giao dịch phân tán |
| **frontend** | [Frontend Ingress & HTTP 500](file:///e:/observability-platform/docs/runbooks/frontend-troubleshooting.md) | Lỗi giao diện người dùng, tỷ lệ 5xx tăng vọt |
| **General** | [General Incident Response](file:///e:/observability-platform/docs/runbooks/general-incident.md) | Quy trình điều tra chung và quản lý vòng đời sự cố |

---

## 🔗 Liên kết Tự Động Với AI Incident Copilot

Mỗi khi hệ thống chẩn đoán ra nguyên nhân gốc rễ (Root Cause Candidate), **AI Incident Copilot** sẽ tự động so khớp và đính kèm link tài liệu Runbook tương ứng trong báo cáo điều tra:
- **Telegram Alert:** Bấm trực tiếp nút `💡 Xem AI Đề xuất Điều tra & Runbook`.
- **Slack Alert:** Bấm nút Block Kit `💡 AI Runbook`.
- **Web UI:** Xem danh mục runbook tại `http://172.16.20.26:30083/api/v1/incidents/<INCIDENT_ID>/recommendations`.
