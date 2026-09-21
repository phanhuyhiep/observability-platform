"""CLI utility to test Telegram Bot configuration and send a mock Incident Alert.

Standalone script with ZERO external dependencies (uses standard library urllib, json, html).

Usage:
  python3 scripts/test_telegram.py
  (automatically reads token & chat_id from k8s/notification-secret.yaml or env vars)
  or
  python3 scripts/test_telegram.py --token <BOT_TOKEN> --chat-id <CHAT_ID>
"""

import argparse
import html
import json
import os
import re
import sys
import urllib.request
import urllib.error

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


def parse_secret_file():
    """Try to read TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID from notification-secret.yaml."""
    secret_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "k8s",
        "notification-secret.yaml",
    )
    token = None
    chat_id = None
    if os.path.exists(secret_path):
        try:
            with open(secret_path, "r", encoding="utf-8") as f:
                content = f.read()
                m_token = re.search(r'TELEGRAM_BOT_TOKEN:\s*["\']?([^"\'\s\n]+)["\']?', content)
                m_chat = re.search(r'TELEGRAM_CHAT_ID:\s*["\']?([^"\'\s\n]+)["\']?', content)
                if m_token and m_token.group(1):
                    token = m_token.group(1).strip()
                if m_chat and m_chat.group(1):
                    chat_id = m_chat.group(1).strip()
        except Exception:
            pass
    return token, chat_id


def verify_bot(token: str) -> dict:
    url = f"https://api.telegram.org/bot{token}/getMe"
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=8) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as e:
        err_body = e.read().decode()
        return {"ok": False, "error": f"HTTP {e.code}: {err_body}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def build_telegram_message(
    incident_id: str,
    title: str,
    severity: str,
    root_cause: str = "Unknown",
    confidence: float = 0.0,
    impacted_services: list = None,
    estimated_user_impact: str = "low",
    grafana_url: str = "http://localhost:30300",
) -> str:
    severity_emoji = {
        "critical": "🚨",
        "high": "⚠️",
        "warning": "⚡",
        "info": "ℹ️",
    }
    emoji = severity_emoji.get(severity.lower(), "📢")
    impacted_str = ", ".join(impacted_services[:6]) if impacted_services else "None"
    if impacted_services and len(impacted_services) > 6:
        impacted_str += f" (+{len(impacted_services) - 6} more)"

    lines = [
        f"{emoji} <b>INCIDENT ALERT: {html.escape(incident_id)}</b>",
        f"<b>Severity:</b> <code>{html.escape(severity.upper())}</code>",
        f"<b>Summary:</b> {html.escape(title)}",
        "",
        f"🎯 <b>Root Cause Candidate:</b> <code>{html.escape(root_cause)}</code>",
        f"📊 <b>Confidence:</b> <code>{confidence * 100:.0f}%</code>",
        f"🌐 <b>User Impact:</b> <code>{html.escape(estimated_user_impact.upper())}</code>",
        f"🔗 <b>Impacted Services:</b> <code>{html.escape(impacted_str)}</code>",
        "",
        f"👉 <a href='{grafana_url}'>Open Incident Dashboard in Grafana</a>",
    ]
    return "\n".join(lines)


def send_telegram_alert(token: str, chat_id: str, html_message: str) -> dict:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": html_message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as e:
        err_body = e.read().decode()
        return {"ok": False, "error": f"HTTP {e.code}: {err_body}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def main():
    default_token, default_chat_id = parse_secret_file()
    if not default_token:
        default_token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not default_chat_id:
        default_chat_id = os.getenv("TELEGRAM_CHAT_ID")

    parser = argparse.ArgumentParser(description="Test Telegram Bot Incident Notifications")
    parser.add_argument("--token", default=default_token, help="Telegram Bot Token")
    parser.add_argument("--chat-id", default=default_chat_id, help="Telegram Chat ID or Group ID")
    parser.add_argument("--grafana-url", default="http://localhost:30300", help="Grafana Web URL")
    args = parser.parse_args()

    print("=================================================================")
    print("🤖 TELEGRAM BOT NOTIFICATION TEST (STANDALONE)")
    print("=================================================================\n")

    if not args.token:
        print("❌ Lỗi: Thiếu Telegram Bot Token!")
        print("👉 Vui lòng điền vào file k8s/notification-secret.yaml hoặc truyền qua --token <TOKEN>")
        sys.exit(1)

    if not args.chat_id:
        print("❌ Lỗi: Thiếu Telegram Chat ID!")
        print("👉 Vui lòng điền vào file k8s/notification-secret.yaml hoặc truyền qua --chat-id <CHAT_ID>")
        sys.exit(1)

    masked_token = args.token[:8] + "..." + args.token[-4:] if len(args.token) > 12 else "***"
    print(f"🔑 Bot Token: {masked_token}")
    print(f"💬 Chat ID:   {args.chat_id}\n")

    # 1. Verify Bot Token
    print(f"[1/2] Đang kiểm tra tính hợp lệ của Bot Token...")
    bot_info = verify_bot(args.token)
    if not bot_info.get("ok"):
        print(f"❌ Bot Token không hợp lệ: {bot_info.get('error')}")
        sys.exit(1)

    bot_user = bot_info.get("result", {})
    print(f"   ✅ Kết nối Bot thành công!")
    print(f"      • Tên Bot: {bot_user.get('first_name')} (@{bot_user.get('username')})")
    print(f"      • Bot ID: {bot_user.get('id')}\n")

    # 2. Build & Send Test Alert
    print(f"[2/2] Đang gửi thông báo sự cố mẫu tới Chat ID [{args.chat_id}]...")
    msg = build_telegram_message(
        incident_id="INC-1001",
        title="Cascading failure across redis-cart, cartservice, and frontend",
        severity="critical",
        root_cause="redis-cart",
        confidence=0.92,
        impacted_services=["redis-cart", "cartservice", "frontend", "checkoutservice"],
        estimated_user_impact="critical",
        grafana_url=args.grafana_url,
    )

    result = send_telegram_alert(args.token, args.chat_id, msg)
    if result.get("ok"):
        print("   ✅ ĐÃ GỬI THÀNH CÔNG VÀO TELEGRAM!")
        print("   📱 Hãy kiểm tra tin nhắn trên ứng dụng Telegram của bạn.")
    else:
        print(f"   ❌ Gửi tin nhắn thất bại: {result.get('error')}")
        print("\n💡 Các lỗi thường gặp:")
        print("   1. 'chat not found' hoặc 'bot was blocked by the user':")
        print("      👉 Bạn cần mở bot trên Telegram và ấn nút 'START' trước khi bot có thể gửi tin cho bạn.")
        print("   2. 'group chat was migrated':")
        print("      👉 Nếu gửi vào nhóm, hãy chắc chắn bot đã được add vào group và cấp quyền Send Messages.")

    print("\n=================================================================")


if __name__ == "__main__":
    main()
