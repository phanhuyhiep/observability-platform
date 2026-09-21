"""Demo Scenario for Phase 4: Root Cause Analysis & Incident Lifecycle.

Demonstrates:
1. Multi-signal Root Cause Scoring & Ranking (Temporal, Topology, Propagation, Severity, Deployment, Evidence).
2. Blast Radius Calculation (Direct, Indirect, and User-Facing Services).
3. Telemetry Evidence Aggregation (Prometheus metrics, Loki logs, Tempo traces).
4. Incident Lifecycle State Transitions (OPEN -> ACK -> INVESTIGATING -> MITIGATED -> RESOLVED) with MTTR calculation.
5. Alert Dispatching to Slack (Block Kit) & Telegram (Markdown).
"""

import json
import subprocess
import time
import urllib.request
import urllib.error


def api_get(url: str):
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=5) as response:
            return json.loads(response.read().decode())
    except urllib.error.URLError as e:
        return {"error": str(e)}


def api_post(url: str, payload: dict):
    try:
        data = json.dumps(payload).encode()
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as response:
            return json.loads(response.read().decode())
    except urllib.error.URLError as e:
        return {"error": str(e)}


def main():
    print("=================================================================")
    print("🚀 DEMO PHASE 4: ROOT CAUSE ANALYSIS & INCIDENT LIFECYCLE")
    print("=================================================================\n")

    base_url = "http://localhost:8082"

    # Step 0: Check Health
    print("[0/5] Kiểm tra kết nối tới RCA Service (Port 8082)...")
    health = api_get(f"{base_url}/health")
    if "error" in health:
        print(f"❌ Không thể kết nối tới RCA Service: {health['error']}")
        print("💡 Hãy chạy port-forward trước: kubectl port-forward svc/rca-service 8082:8082 -n observability")
        return
    print(f"   ✅ RCA Service đang hoạt động! Trạng thái: {health.get('status')}\n")

    # Step 1: Lấy danh sách hoặc chọn Incident ID (mặc định INC-1001)
    incident_id = "INC-1001"
    print(f"[1/5] Đang phân tích sự cố Root Cause cho [{incident_id}]...")
    rca = api_get(f"{base_url}/api/v1/root-causes/{incident_id}")

    if "error" in rca:
        print(f"⚠️ Chưa có dữ liệu sự cố {incident_id} ({rca['error']}). Dùng sự cố mẫu...")
    else:
        print(f"   🎯 Nguyên nhân gốc rễ dự đoán: [{rca.get('top_root_cause')}]")
        print(f"   📊 Độ tin cậy (Confidence): {rca.get('confidence', 0.0) * 100:.1f}%")
        print("   🏆 Bảng xếp hạng ứng viên (Ranked Candidates):")
        for c in rca.get("root_causes", []):
            sb = c.get("scores_breakdown", {})
            print(f"      #{c['rank']} [{c['entity_id']}] (Điểm: {c['score']:.2f}, Loại: {c['entity_type']})")
            print(f"         • Temporal: {sb.get('temporal'):.2f} | Topology: {sb.get('topology'):.2f} | Severity: {sb.get('severity'):.2f}")
    print()

    # Step 2: Tính toán Blast Radius
    print(f"[2/5] Đang phân tích Blast Radius cho [{incident_id}]...")
    blast = api_get(f"{base_url}/api/v1/root-causes/{incident_id}/blast-radius")
    if "blast_radius" in blast:
        br = blast["blast_radius"]
        print(f"   💥 Mức độ ảnh hưởng người dùng: {br.get('estimated_user_impact', 'unknown').upper()}")
        print(f"   ⚠️ Dịch vụ ảnh hưởng trực tiếp (1-hop): {br.get('direct_impact')}")
        print(f"   🌊 Dịch vụ lan truyền gián tiếp (2+ hops): {br.get('indirect_impact')}")
        print(f"   🌐 Dịch vụ giao diện người dùng bị tác động: {br.get('user_facing_services')}")
        print(f"   📊 Tổng số service bị ảnh hưởng: {br.get('total_impacted')}")
    print()

    # Step 3: Tổng hợp Bằng chứng (Telemetry Evidence)
    print(f"[3/5] Đang thu thập bằng chứng đa tín hiệu (Prometheus, Loki, Tempo)...")
    evidence = api_get(f"{base_url}/api/v1/incidents/{incident_id}/evidence")
    if "evidence" in evidence:
        print(f"   📋 Thu thập được {evidence.get('total_evidence')} bằng chứng xác thực:")
        for ev in evidence.get("evidence", [])[:4]:
            print(f"      • [{ev['type'].upper()}] {ev['description']}")
            print(f"        🔗 Grafana Link: {ev.get('grafana_link')}")
    print()

    # Step 4: Quy trình xử lý sự cố (Incident Lifecycle & MTTR)
    print(f"[4/5] Mô phỏng vòng đời xử lý sự cố bởi SRE (Incident Lifecycle)...")
    # Acknowledge
    ack = api_post(f"{base_url}/api/v1/incidents/{incident_id}/acknowledge", {"actor": "SRE-Oncall", "comment": "Đã tiếp nhận cảnh báo"})
    print(f"   1. [ACKNOWLEDGED] Kỹ sư SRE đã nhận sự cố: {ack.get('status')}")

    # Investigate
    inv = api_post(f"{base_url}/api/v1/incidents/{incident_id}/investigate", {"actor": "SRE-Oncall", "comment": "Đang kiểm tra redis connection pool"})
    print(f"   2. [INVESTIGATING] Chuyển trạng thái điều tra: {inv.get('status')}")

    # Comment
    com = api_post(f"{base_url}/api/v1/incidents/{incident_id}/comment", {"actor": "SRE-Oncall", "comment": "Phát hiện Redis chạm ngưỡng 98% memory. Tiến hành mở rộng bộ nhớ."})
    print(f"   3. [COMMENT] Đã ghi chú nhật ký điều tra: {com.get('status')}")

    # Resolve
    res = api_post(f"{base_url}/api/v1/incidents/{incident_id}/resolve", {"actor": "SRE-Oncall", "comment": "Bộ nhớ redis đã giải phóng, latency đã về dưới 20ms"})
    print(f"   4. [RESOLVED] Đã khắc phục xong sự cố!")
    if res.get("mttr_seconds"):
        print(f"      ⏱️ MTTR (Thời gian phục hồi): {res['mttr_seconds']:.1f} giây ({res['mttr_seconds']/60:.2f} phút)")
    print()

    # Step 5: Thử nghiệm Dispatch Thông Báo
    print(f"[5/5] Kiểm tra phát thông báo cảnh báo đa kênh (Slack Block Kit / Telegram)...")
    notify = api_post(f"{base_url}/api/v1/notifications/test", {"channel": "all", "test_incident_id": incident_id})
    print(f"   📢 Kết quả phát thông báo: {notify.get('status')}")
    print(f"   📡 Chi tiết kênh gửi: {notify.get('details')}")

    print("\n=================================================================")
    print("🎉 DEMO PHASE 4 HOÀN TẤT THÀNH CÔNG!")
    print("=================================================================")


if __name__ == "__main__":
    main()
