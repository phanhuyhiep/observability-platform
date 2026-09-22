"""Chaos & Failure Injection Simulator for Cloud-Native Observability Platform.

Simulates real-world microservices failure modes and cascading disasters:
1. redis-down: Scale down redis-cart to 0 replicas (Dependency Crash).
2. bad-deployment: Misconfigure cartservice environment to invalid Redis address (Rollout Failure).
3. traffic-surge: Scale up loadgenerator to flood the cluster (Traffic Spike).
4. telemetry-cascade: Inject a multi-tier cascading anomaly directly into database to test RCA & Alerts.
5. restore: Restore all services back to healthy baseline.

Usage:
  python3 scripts/chaos_simulator.py --scenario redis-down
  python3 scripts/chaos_simulator.py --scenario bad-deployment
  python3 scripts/chaos_simulator.py --scenario traffic-surge
  python3 scripts/chaos_simulator.py --scenario telemetry-cascade
  python3 scripts/chaos_simulator.py --scenario restore
"""

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request
import urllib.error

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


def run_cmd(cmd: list[str]) -> tuple[int, str, str]:
    """Execute shell command and capture stdout/stderr."""
    try:
        p = subprocess.run(cmd, capture_output=True, text=True)
        return p.returncode, p.stdout.strip(), p.stderr.strip()
    except Exception as e:
        return 1, "", str(e)


def scenario_redis_down():
    print("=================================================================")
    print("💥 SCENARIO 1: LEAF DEPENDENCY FAILURE (REDIS-CART CRASH)")
    print("=================================================================\n")
    print("📝 Mô tả:")
    print("   Hạ replicas của `redis-cart` về 0 để giả lập sập database bộ nhớ đệm.")
    print("   Hệ quả lan truyền:")
    print("   • `cartservice` mất kết nối Redis -> quăng Exception liên tục.")
    print("   • `frontend` khi gọi cartservice bị timeout / HTTP 500.")
    print("   • RCA Engine sẽ phân tích và xếp hạng `redis-cart` là Root Cause #1.\n")

    print("[1/2] Đang tắt pod redis-cart (scale replicas = 0)...")
    code, out, err = run_cmd(["kubectl", "scale", "deployment/redis-cart", "--replicas=0"])
    if code != 0:
        print(f"❌ Lỗi scale redis-cart: {err}")
        return
    print("   ✅ Đã tắt redis-cart thành công!")

    print("\n[2/2] Đang tạo traffic gọi vào Cart Service để ép sinh lỗi 500 & Exception...")
    # Exec curl vào frontend để gọi /cart
    for i in range(5):
        run_cmd(["kubectl", "exec", "deployment/frontend", "--", "curl", "-s", "http://localhost:8080/cart"])
        time.sleep(1)
    print("   ✅ Đã bắn 5 requests vào cart service (cartservice đã văng exception vì mất Redis)!")

    print("\n📊 Kiểm tra trạng thái pods hiện tại:")
    _, out, _ = run_cmd(["kubectl", "get", "pods", "-l", "app in (redis-cart,cartservice,frontend)"])
    print(out)

    print("\n⏱️ LƯU Ý VỀ THỜI GIAN PHÁT HIỆN (DETECTION PIPELINE):")
    print("   • Prometheus cào metrics mỗi 15s - 30s.")
    print("   • Detection Service chạy đánh giá Z-Score mỗi 30s.")
    print("   • Correlation Engine gom Incident mỗi 30s.")
    print("   👉 Hãy để pod redis-cart ở trạng thái tắt trong khoảng 30s - 1 phút trước khi restore,")
    print("      hoặc chạy lệnh: python3 scripts/chaos_simulator.py --scenario telemetry-cascade để nổ alert tức thì!\n")

    print("👉 BƯỚC TIẾP THEO:")
    print("   1. Xem log lỗi cartservice văng ra: kubectl logs -l app=cartservice --tail=20")
    print("   2. Xem dashboard Grafana cập nhật: http://localhost:30300 (hoặc port 4000)")
    print("   3. Sau khi quan sát xong, khôi phục lại: python3 scripts/chaos_simulator.py --scenario restore")


def scenario_bad_deployment():
    print("=================================================================")
    print("🚀 SCENARIO 2: BAD DEPLOYMENT / ROLLOUT FAILURE")
    print("=================================================================\n")
    print("📝 Mô tả:")
    print("   Giả lập kỹ sư DevOps cấu hình sai REDIS_ADDR khi rollout `cartservice`.")
    print("   Hệ quả:")
    print("   • `cartservice` rollout pod mới và crashloop hoặc không kết nối được.")
    print("   • `deployment_correlator` bắt sự kiện rollout và đối soát thời gian.")
    print("   • `DeploymentScorer` cộng điểm tối đa (1.0) cho `cartservice`!\n")

    print("[1/2] Cấu hình sai địa chỉ REDIS_ADDR cho cartservice...")
    code, out, err = run_cmd([
        "kubectl", "set", "env", "deployment/cartservice",
        "REDIS_ADDR=invalid-redis-host:6379"
    ])
    if code != 0:
        print(f"❌ Lỗi set env: {err}")
        return
    print("   ✅ Đã cập nhật REDIS_ADDR sai cấu hình!")

    print("\n[2/2] Bắn Webhook sự kiện Deployment vào Correlation Engine (port 8081)...")
    payload = {
        "service": "cartservice",
        "namespace": "default",
        "version": "v2.1.0-buggy",
        "deployed_by": "ci-cd-pipeline",
        "status": "completed",
    }
    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            "http://localhost:8081/api/v1/deployments",
            data=data,
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=5) as res:
            print(f"   ✅ Đã ghi nhận Deployment event: {res.read().decode()}")
    except Exception as e:
        print(f"   ℹ️ Không kết nối được Webhook port 8081 ({e}), bỏ qua bước webhook.")

    print("\n👉 BƯỚC TIẾP THEO:")
    print("   1. Quan sát pod rollout: kubectl get pods -l app=cartservice -w")
    print("   2. Xem RCA phân tích nguyên nhân do deployment:")
    print("      curl http://localhost:8082/api/v1/root-causes/INC-1001")
    print("   3. Để khôi phục cấu hình: python3 scripts/chaos_simulator.py --scenario restore")


def scenario_traffic_surge():
    print("=================================================================")
    print("🌊 SCENARIO 3: TRAFFIC SURGE (TĂNG TẢI ĐỘT BIẾN)")
    print("=================================================================\n")
    print("📝 Mô tả:")
    print("   Tăng gấp 4 lần số replica của `loadgenerator` để dội traffic cực lớn vào hệ thống.")
    print("   Hệ quả:")
    print("   • CPU & Latency của `frontend` và `productcatalogservice` tăng vọt.")
    print("   • Z-Score Detector và EWMA Detector của Phase 2 sẽ phát hiện bất thường.")

    print("\n[1/1] Scale loadgenerator lên 4 replicas...")
    code, out, err = run_cmd(["kubectl", "scale", "deployment/loadgenerator", "--replicas=4"])
    if code != 0:
        print(f"❌ Lỗi scale loadgenerator: {err}")
        return
    print("   ✅ Đã kích hoạt 4 loadgenerator pods!")
    print("   ⏳ Traffic đang đổ về frontend. Kiểm tra metrics trên Grafana...")


def scenario_telemetry_cascade():
    print("=================================================================")
    print("⚡ SCENARIO 4: INJECT TELEMETRY CASCADE (MULTI-TIER INCIDENT)")
    print("=================================================================\n")
    print("📝 Mô tả:")
    print("   Nạp trực tiếp chuỗi 4 bất thường liên hoàn vào Database:")
    print("   1. redis-cart     -> Latency 520ms (Z-Score 5.1, Critical)")
    print("   2. cartservice    -> Latency 980ms (Z-Score 4.6, High)")
    print("   3. checkoutservice-> Timeout & Error 5xx (Z-Score 4.2, High)")
    print("   4. frontend       -> HTTP 500 error rate 22% (Z-Score 5.8, Critical)\n")

    sql = """
    INSERT INTO anomaly_events (
        anomaly_id, timestamp, detected_at, entity_type, entity_id, namespace, cluster,
        detector, category, signal, severity, score, confidence, current_value, baseline_mean, z_score, status
    ) VALUES 
    (
        gen_random_uuid(), now() - interval '3 minutes', now() - interval '3 minutes',
        'database', 'redis-cart', 'default', 'minikube',
        'zscore', 'latency', 'redis_command_duration_seconds', 'critical',
        5.1, 0.95, 0.520, 0.020, 5.1, 'active'
    ),
    (
        gen_random_uuid(), now() - interval '2 minutes', now() - interval '2 minutes',
        'service', 'cartservice', 'default', 'minikube',
        'zscore', 'latency', 'http_request_duration_seconds', 'high',
        4.6, 0.91, 0.980, 0.045, 4.6, 'active'
    ),
    (
        gen_random_uuid(), now() - interval '90 seconds', now() - interval '90 seconds',
        'service', 'checkoutservice', 'default', 'minikube',
        'zscore', 'latency', 'grpc_client_duration_seconds', 'high',
        4.2, 0.88, 1.250, 0.060, 4.2, 'active'
    ),
    (
        gen_random_uuid(), now() - interval '30 seconds', now() - interval '30 seconds',
        'service', 'frontend', 'default', 'minikube',
        'ewma', 'error_rate', 'http_5xx_rate', 'critical',
        5.8, 0.98, 0.220, 0.005, 5.8, 'active'
    );
    """

    print("[1/3] Đang nạp SQL anomalies vào detection-postgres...")
    cmd = [
        "kubectl", "exec", "-i", "deployment/detection-postgres", "-n", "observability",
        "--", "psql", "-U", "detection", "-d", "detection_db"
    ]
    p = subprocess.run(cmd, input=sql, text=True, capture_output=True)
    if p.returncode != 0:
        print(f"❌ Lỗi nạp database: {p.stderr}")
        return
    print("   ✅ Đã nạp thành công 4 bất thường liên hoàn vào Database!")

    print("\n[2/3] Kích hoạt Correlation Engine (port 8081) đánh giá gom Incident...")
    try:
        req = urllib.request.Request(
            "http://localhost:8081/api/v1/correlations/evaluate",
            data=b"{}",
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=5) as res:
            res_json = json.loads(res.read().decode())
            print(f"   Response Correlation: {res_json.get('status')}")
    except Exception as e:
        print(f"   ℹ️ Correlation API: {e}")

    print("\n[3/3] Kích hoạt RCA Engine & Dispatch Alert Telegram (port 8082)...")
    try:
        req = urllib.request.Request("http://localhost:8082/api/v1/root-causes/INC-1001")
        with urllib.request.urlopen(req, timeout=5) as res:
            rca_res = json.loads(res.read().decode())
            print(f"   🎯 Nguyên nhân gốc dự đoán: {rca_res.get('top_root_cause')}")
            print(f"   📊 Độ tin cậy: {rca_res.get('confidence', 0)*100:.1f}%")
            print("   📢 Đã tự động kích hoạt thông báo Telegram!")
    except Exception as e:
        print(f"   ℹ️ RCA API: {e}")

    print("\n=================================================================")
    print("🎉 ĐÃ TẠO SỰ CỐ GIẢ LẬP THÀNH CÔNG! HÃY KIỂM TRA TELEGRAM & GRAFANA!")
    print("=================================================================")


def scenario_restore():
    print("=================================================================")
    print("🔄 RESTORING SYSTEM TO HEALTHY BASELINE")
    print("=================================================================\n")

    print("[1/3] Khôi phục redis-cart về 1 replica...")
    run_cmd(["kubectl", "scale", "deployment/redis-cart", "--replicas=1"])

    print("[2/3] Khôi phục cấu hình đúng REDIS_ADDR cho cartservice...")
    run_cmd([
        "kubectl", "set", "env", "deployment/cartservice",
        "REDIS_ADDR=redis-cart:6379"
    ])

    print("[3/3] Khôi phục loadgenerator về 1 replica...")
    run_cmd(["kubectl", "scale", "deployment/loadgenerator", "--replicas=1"])

    print("\n⏳ Đang chờ pods trở về trạng thái Ready...")
    time.sleep(4)
    _, out, _ = run_cmd(["kubectl", "get", "pods", "-l", "app in (redis-cart,cartservice,frontend,loadgenerator)"])
    print(out)

    print("\n✅ HỆ THỐNG ĐÃ ĐƯỢC PHỤC HỒI BÌNH THƯỜNG!")


def main():
    parser = argparse.ArgumentParser(description="Chaos & Failure Injection Simulator")
    parser.add_argument(
        "--scenario",
        choices=["redis-down", "bad-deployment", "traffic-surge", "telemetry-cascade", "restore"],
        required=True,
        help="Chọn kịch bản lỗi giả lập",
    )
    args = parser.parse_args()

    if args.scenario == "redis-down":
        scenario_redis_down()
    elif args.scenario == "bad-deployment":
        scenario_bad_deployment()
    elif args.scenario == "traffic-surge":
        scenario_traffic_surge()
    elif args.scenario == "telemetry-cascade":
        scenario_telemetry_cascade()
    elif args.scenario == "restore":
        scenario_restore()


if __name__ == "__main__":
    main()
