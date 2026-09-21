"""Demo Scenario for Phase 3: Cascading Failure & Incident Correlation.

Simulates:
1. Downstream database (redis-cart) latency spike.
2. Middle-tier service (cartservice) latency cascade.
3. Frontend user-facing (frontend) error rate surge.
Then triggers correlation and prints the resulting Incident and Root Cause!
"""

import json
import subprocess
import time
from datetime import datetime, timezone

SQL_INJECT = """
INSERT INTO anomaly_events (
    anomaly_id, timestamp, detected_at, entity_type, entity_id, namespace, cluster,
    detector, category, signal, severity, score, confidence, current_value, baseline_mean, z_score, status
) VALUES 
(
    gen_random_uuid(), now() - interval '2 minutes', now() - interval '2 minutes',
    'database', 'redis-cart', 'default', 'minikube',
    'zscore', 'latency', 'redis_command_duration_seconds', 'high',
    4.5, 0.92, 0.450, 0.025, 4.5, 'active'
),
(
    gen_random_uuid(), now() - interval '90 seconds', now() - interval '90 seconds',
    'service', 'cartservice', 'default', 'minikube',
    'zscore', 'latency', 'http_request_duration_seconds', 'high',
    4.1, 0.89, 0.850, 0.050, 4.1, 'active'
),
(
    gen_random_uuid(), now() - interval '30 seconds', now() - interval '30 seconds',
    'service', 'frontend', 'default', 'minikube',
    'ewma', 'error_rate', 'http_5xx_rate', 'critical',
    5.2, 0.95, 0.150, 0.005, 5.2, 'active'
);
"""


def main():
    print("=================================================================")
    print("🚀 DEMO PHASE 3: CASCADING ANOMALY & INCIDENT CORRELATION")
    print("=================================================================\n")

    # Step 1: Inject Cascading Anomalies
    print("[1/3] Đang nạp chuỗi 3 bất thường liên hoàn vào Database:")
    print("   1. redis-cart  -> Latency tăng vọt (450ms, Z-Score 4.5)")
    print("   2. cartservice -> Latency tăng theo (850ms, Z-Score 4.1)")
    print("   3. frontend    -> Error rate 5xx chạm ngưỡng critical (15%)")

    cmd = [
        "kubectl", "exec", "-i", "deployment/detection-postgres", "-n", "observability",
        "--", "psql", "-U", "detection", "-d", "detection_db"
    ]
    p = subprocess.run(cmd, input=SQL_INJECT, text=True, capture_output=True)
    if p.returncode != 0:
        print(f"❌ Lỗi nạp database: {p.stderr}")
        return
    print("   ✅ Đã nạp thành công vào PostgreSQL!\n")

    # Step 2: Trigger Evaluation
    print("[2/3] Đang kích hoạt Correlation Engine đánh giá (API /evaluate)...")
    eval_cmd = ["curl", "-s", "-X", "POST", "http://localhost:8081/api/v1/correlations/evaluate"]
    eval_res = subprocess.run(eval_cmd, capture_output=True, text=True)
    print(f"   Response: {eval_res.stdout.strip()}\n")

    time.sleep(1)

    # Step 3: Fetch Created Incidents
    print("[3/3] Kết quả phân tích sự cố (Incident) từ Correlation Engine:")
    inc_cmd = ["curl", "-s", "http://localhost:8081/api/v1/incidents"]
    inc_res = subprocess.run(inc_cmd, capture_output=True, text=True)
    try:
        data = json.loads(inc_res.stdout)
        items = data.get("items", [])
        if not items:
            print("   ⚠️ Chưa tìm thấy incident. Đợi 5s rồi thử lại...")
            time.sleep(5)
            inc_res = subprocess.run(inc_cmd, capture_output=True, text=True)
            data = json.loads(inc_res.stdout)
            items = data.get("items", [])

        if items:
            inc = items[0]
            print("   --------------------------------------------------------------")
            print(f"   🔥 INCIDENT ID:        {inc.get('incident_id')}")
            print(f"   📌 TIÊU ĐỀ:             {inc.get('title')}")
            print(f"   ⚠️ MỨC ĐỘ (SEVERITY):  {inc.get('severity').upper()}")
            print(f"   📊 SỐ ANOMALIES GỘP:   {inc.get('anomaly_count')} anomalies")
            print(f"   🎯 CÁC SERVICE BỊ ẢNH HƯỞNG: {', '.join(inc.get('impacted_entities', []))}")

            top = inc.get("topology_context") or {}
            print(f"\n   🧠 PHÂN TÍCH NGUYÊN NHÂN GỐC (TOPOLOGY CONTEXT):")
            print(f"      - Ứng viên nguyên nhân gốc: {top.get('root_entity_candidate')}")
            print(f"      - Độ tin cậy (Confidence):  {top.get('topology_confidence', 0) * 100}%")
            print(f"      - Hướng lan truyền:         {top.get('propagation_direction')}")
            chains = top.get("dependency_chains", [])
            if chains:
                print(f"      - Chuỗi phụ thuộc lỗi:      {chains[0]}")
            print("   --------------------------------------------------------------")
            print("\n🎉 THÀNH CÔNG: Correlation Engine đã gom 3 cảnh báo riêng lẻ thành 1 Incident có ngữ cảnh đầy đủ!")
        else:
            print("   Chưa có incident nào được tạo.")
    except Exception as e:
        print(f"Error parsing response: {e}, raw: {inc_res.stdout}")


if __name__ == "__main__":
    main()
