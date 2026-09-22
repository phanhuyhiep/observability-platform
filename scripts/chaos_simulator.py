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


def run_cmd_stdin(cmd: list[str], input_text: str) -> tuple[int, str, str]:
    """Execute shell command with stdin input."""
    try:
        p = subprocess.run(cmd, input=input_text, capture_output=True, text=True)
        return p.returncode, p.stdout.strip(), p.stderr.strip()
    except Exception as e:
        return 1, "", str(e)


def get_telegram_credentials() -> tuple[str | None, str | None]:
    """Extract Telegram credentials from k8s/notification-secret.yaml or environment."""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if token and chat_id:
        return token, chat_id

    secret_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "services", "rca-service", "k8s", "notification-secret.yaml",
    )
    if os.path.exists(secret_path):
        try:
            import re
            with open(secret_path, "r", encoding="utf-8") as f:
                content = f.read()
                m_t = re.search(r'TELEGRAM_BOT_TOKEN:\s*["\']?([^"\'\s\n]+)["\']?', content)
                m_c = re.search(r'TELEGRAM_CHAT_ID:\s*["\']?([^"\'\s\n]+)["\']?', content)
                if m_t:
                    token = m_t.group(1).strip()
                if m_c:
                    chat_id = m_c.group(1).strip()
        except Exception:
            pass
    return token, chat_id


def send_telegram_alert(
    incident_id: str,
    title: str,
    severity: str,
    root_cause: str,
    confidence: float,
    impacted: list[str],
    grafana_url: str = "http://172.16.20.26:4000",
) -> bool:
    """Send HTML incident alert to Telegram directly."""
    import html
    token, chat_id = get_telegram_credentials()
    if not token or not chat_id:
        print("   ⚠️ Không tìm thấy Telegram token/chat_id trong k8s/notification-secret.yaml")
        return False

    emoji_map = {"critical": "🚨", "high": "⚠️", "warning": "⚡"}
    emoji = emoji_map.get(severity.lower(), "📢")
    impacted_str = ", ".join(impacted) if impacted else "None"

    msg = (
        f"{emoji} <b>INCIDENT ALERT: {html.escape(incident_id)}</b>\n"
        f"<b>Severity:</b> <code>{html.escape(severity.upper())}</code>\n"
        f"<b>Summary:</b> {html.escape(title)}\n\n"
        f"🎯 <b>Root Cause Candidate:</b> <code>{html.escape(root_cause)}</code>\n"
        f"📊 <b>Confidence:</b> <code>{confidence * 100:.0f}%</code>\n"
        f"🌐 <b>User Impact:</b> <code>CRITICAL (Cart/Checkout Broken)</code>\n"
        f"🔗 <b>Impacted Services:</b> <code>{html.escape(impacted_str)}</code>\n\n"
        f"👉 <a href='{grafana_url}'>Open Incident Dashboard in Grafana</a>"
    )

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps({
        "chat_id": chat_id,
        "text": msg,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            if resp.status == 200:
                print(f"   📱 [TELEGRAM] Đã bắn cảnh báo sự cố {incident_id} tới điện thoại thành công!")
                return True
    except Exception as e:
        print(f"   ⚠️ Lỗi gửi tin nhắn Telegram: {e}")
    return False


def get_slack_webhook_url() -> str | None:
    """Extract Slack Webhook URL from notification-secret.yaml or environment."""
    url = os.getenv("SLACK_WEBHOOK_URL")
    if url:
        return url
    secret_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "services", "rca-service", "k8s", "notification-secret.yaml",
    )
    if os.path.exists(secret_path):
        try:
            import re
            with open(secret_path, "r", encoding="utf-8") as f:
                content = f.read()
                m = re.search(r'SLACK_WEBHOOK_URL:\s*["\']?([^"\'\s\n]+)["\']?', content)
                if m and m.group(1).startswith("http"):
                    return m.group(1).strip()
        except Exception:
            pass
    return None


def send_slack_alert(
    incident_id: str,
    title: str,
    severity: str,
    root_cause: str,
    confidence: float,
    impacted: list[str],
    grafana_url: str = "http://172.16.20.26:4000",
) -> bool:
    """Send Slack Block Kit interactive card via incoming webhook."""
    webhook_url = get_slack_webhook_url()
    if not webhook_url:
        return False

    emoji_map = {"critical": "🔴", "high": "🟠", "warning": "🟡", "info": "🔵"}
    emoji = emoji_map.get(severity.lower(), "⚪")
    impacted_str = ", ".join(impacted) if impacted else "None"

    payload = {
        "blocks": [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{emoji} Incident {incident_id} | {severity.upper()}",
                    "emoji": True,
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*{title}*",
                },
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Root Cause:*\n`{root_cause}` ({confidence * 100:.0f}% confidence)",
                    },
                    {
                        "type": "mrkdwn",
                        "text": "*User Impact:*\n`CRITICAL`",
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Impacted Services:*\n{impacted_str}",
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Dashboard:*\n<{grafana_url}|View in Grafana>",
                    },
                ],
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Acknowledge"},
                        "style": "primary",
                        "value": f"ack_{incident_id}",
                    },
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Investigate Traces (Tempo)"},
                        "url": f"{grafana_url}/explore?orgId=1&left=%7B%22datasource%22:%22tempo%22,%22queries%22:%5B%7B%22refId%22:%22A%22,%22queryType%22:%22search%22%7D%5D%7D",
                    },
                ],
            },
        ]
    }

    req = urllib.request.Request(
        webhook_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            if resp.status == 200:
                print(f"   💬 [SLACK] Đã bắn thẻ cảnh báo Block Kit tới kênh Slack thành công!")
                return True
    except Exception as e:
        print(f"   ⚠️ Lỗi gửi tin nhắn Slack: {e}")
    return False


def insert_incident_to_db(
    incident_id: str,
    title: str,
    severity: str,
    root_cause: str,
    impacted: list[str],
    confidence: float = 0.94,
) -> bool:
    """Directly insert an incident into PostgreSQL detection_db."""
    impacted_json = json.dumps(impacted)
    sql = f"""
    INSERT INTO incidents (
        incident_id, title, severity, status, created_at, updated_at,
        anomaly_count, entity_count, impacted_entities, namespaces, cluster,
        topology_context, metadata
    ) VALUES (
        '{incident_id}',
        '{title}',
        '{severity.upper()}',
        'OPEN',
        now(),
        now(),
        {len(impacted)},
        {len(impacted)},
        '{impacted_json}'::jsonb,
        '["default"]'::jsonb,
        'minikube',
        '{{"root_entity_candidate": "{root_cause}", "confidence": {confidence}, "algorithm": "random_walk"}}'::jsonb,
        '{{"root_candidate": "{root_cause}", "source": "chaos_injection"}}'::jsonb
    ) ON CONFLICT (incident_id) DO NOTHING;

    INSERT INTO incident_timeline_events (incident_id, timestamp, event_type, actor, title, description)
    VALUES (
        '{incident_id}',
        now(),
        'incident_created',
        'detection-service',
        'Status: OPEN',
        '{title}'
    );
    """
    cmd = [
        "kubectl", "exec", "-i", "deployment/detection-postgres", "-n", "observability",
        "--", "psql", "-U", "detection", "-d", "detection_db"
    ]
    code, out, err = run_cmd_stdin(cmd, sql)
    if code == 0:
        print(f"   📊 [GRAFANA] Đã ghi nhận sự cố {incident_id} vào Database thành công!")
        return True
    else:
        print(f"   ⚠️ Lỗi ghi Database: {err}")
        return False


def scenario_redis_down():
    print("=================================================================")
    print("💥 SCENARIO 1: LEAF DEPENDENCY FAILURE (REDIS-CART CRASH)")
    print("=================================================================")
    print("\n📝 Mô tả:")
    print("   Hạ replicas của `redis-cart` về 0 để giả lập sập database bộ nhớ đệm.")
    print("   Hệ quả lan truyền:")
    print("   • `cartservice` mất kết nối Redis -> quăng Exception liên tục.")
    print("   • `frontend` khi gọi cartservice bị timeout / HTTP 500.")
    print("   • RCA Engine xếp hạng `redis-cart` là Root Cause #1.\n")

    print("[1/3] Đang tắt pod redis-cart (scale replicas = 0)...")
    code, out, err = run_cmd(["kubectl", "scale", "deployment/redis-cart", "--replicas=0"])
    if code != 0:
        print(f"❌ Lỗi scale redis-cart: {err}")
        return
    print("   ✅ Đã tắt redis-cart thành công!")

    print("\n[2/3] Đang tạo traffic gọi vào Cart Service để sinh Exception thực tế...")
    for i in range(5):
        run_cmd(["kubectl", "exec", "deployment/frontend", "--", "curl", "-s", "http://localhost:8080/cart"])
        time.sleep(0.5)
    print("   ✅ Đã kích hoạt 5 requests (cartservice đã văng exception vì mất Redis)!")

    print("\n[3/3] Kích hoạt sự cố & gửi thông báo Telegram tức thì...")
    inc_num = int(time.time()) % 900000 + 100000
    incident_id = f"INC-{inc_num}"
    title = "[redis-cart] database crash causing cascade to cartservice, frontend"
    insert_incident_to_db(
        incident_id=incident_id,
        title=title,
        severity="CRITICAL",
        root_cause="redis-cart",
        impacted=["redis-cart", "cartservice", "frontend"],
        confidence=0.95,
    )
    send_telegram_alert(
        incident_id=incident_id,
        title=title,
        severity="CRITICAL",
        root_cause="redis-cart",
        confidence=0.95,
        impacted=["redis-cart", "cartservice", "frontend"],
    )
    send_slack_alert(
        incident_id=incident_id,
        title=title,
        severity="CRITICAL",
        root_cause="redis-cart",
        confidence=0.95,
        impacted=["redis-cart", "cartservice", "frontend"],
    )

    print("\n=================================================================")
    print("🎉 SỰ CỐ ĐÃ ĐƯỢC KÍCH HOẠT THÀNH CÔNG!")
    print(f"   • Mã sự cố: {incident_id}")
    print("   • Hãy kiểm tra điện thoại Telegram để xem tin nhắn báo động đỏ!")
    print("   • Mở Grafana (F5) xem dòng đầu tiên trên bảng 'Incident Intelligence Table'!")
    print("   • Click vào mã sự cố trên bảng để mở Data Links xem chi tiết.")
    print("   • Khi test xong, chạy: python3 scripts/chaos_simulator.py --scenario restore")
    print("=================================================================\n")


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

    print("\n[2/3] Nạp Incident liên hoàn vào Database...")
    inc_num = int(time.time()) % 900000 + 100000
    incident_id = f"INC-{inc_num}"
    title = "[redis-cart] multi-tier anomaly cascade to cartservice, checkoutservice, frontend"
    insert_incident_to_db(
        incident_id=incident_id,
        title=title,
        severity="CRITICAL",
        root_cause="redis-cart",
        impacted=["redis-cart", "cartservice", "checkoutservice", "frontend"],
        confidence=0.96,
    )

    print("\n[3/3] Gửi thông báo báo động đỏ tới Telegram...")
    send_telegram_alert(
        incident_id=incident_id,
        title=title,
        severity="CRITICAL",
        root_cause="redis-cart",
        confidence=0.96,
        impacted=["redis-cart", "cartservice", "checkoutservice", "frontend"],
    )
    send_slack_alert(
        incident_id=incident_id,
        title=title,
        severity="CRITICAL",
        root_cause="redis-cart",
        confidence=0.96,
        impacted=["redis-cart", "cartservice", "checkoutservice", "frontend"],
    )

    print("\n=================================================================")
    print("🎉 ĐÃ TẠO SỰ CỐ GIẢ LẬP THÀNH CÔNG! HÃY KIỂM TRA TELEGRAM & GRAFANA!")
    print(f"   • Mã sự cố: {incident_id}")
    print("   • F5 lại Grafana để thấy sự cố nổ đỏ trên bảng 'Incident Intelligence Table'!")
    print("   • Click vào mã sự cố trên bảng để mở Data Links chi tiết.")
    print("=================================================================\n")


def scenario_restore():
    print("=================================================================")
    print("🔄 RESTORING SYSTEM TO HEALTHY BASELINE")
    print("=================================================================\n")

    print("[1/4] Khôi phục redis-cart về 1 replica...")
    run_cmd(["kubectl", "scale", "deployment/redis-cart", "--replicas=1"])

    print("[2/4] Khôi phục cấu hình đúng REDIS_ADDR cho cartservice...")
    run_cmd([
        "kubectl", "set", "env", "deployment/cartservice",
        "REDIS_ADDR=redis-cart:6379"
    ])

    print("[3/4] Khôi phục loadgenerator về 1 replica...")
    run_cmd(["kubectl", "scale", "deployment/loadgenerator", "--replicas=1"])

    print("[4/4] Tự động cập nhật các sự cố đang OPEN sang RESOLVED...")
    sql_resolve = """
    UPDATE incidents
    SET status = 'RESOLVED',
        resolved_at = now(),
        updated_at = now(),
        mttr_seconds = EXTRACT(EPOCH FROM (now() - created_at))
    WHERE status = 'OPEN';

    INSERT INTO incident_timeline_events (incident_id, timestamp, event_type, actor, title, description)
    SELECT incident_id, now(), 'state_change', 'chaos-simulator', 'Status: RESOLVED', 'Service restored to healthy baseline'
    FROM incidents
    WHERE status = 'RESOLVED' AND resolved_at >= now() - interval '1 minute';
    """
    cmd = [
        "kubectl", "exec", "-i", "deployment/detection-postgres", "-n", "observability",
        "--", "psql", "-U", "detection", "-d", "detection_db"
    ]
    run_cmd_stdin(cmd, sql_resolve)

    print("\n⏳ Đang chờ pods trở về trạng thái Ready...")
    time.sleep(4)
    _, out, _ = run_cmd(["kubectl", "get", "pods", "-l", "app in (redis-cart,cartservice,frontend,loadgenerator)"])
    print(out)

    print("\n✅ HỆ THỐNG ĐÃ ĐƯỢC PHỤC HỒI BÌNH THƯỜNG & SỰ CỐ ĐÃ ĐƯỢC RESOLVED!")


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
