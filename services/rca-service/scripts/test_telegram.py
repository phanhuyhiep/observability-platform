"""CLI utility to test Telegram Bot configuration and send a mock Incident Alert.

Usage:
  python3 scripts/test_telegram.py --token <BOT_TOKEN> --chat-id <CHAT_ID>
  or
  export TELEGRAM_BOT_TOKEN="your_bot_token"
  export TELEGRAM_CHAT_ID="your_chat_id"
  python3 scripts/test_telegram.py
"""

import argparse
import json
import os
import sys
import urllib.request
import urllib.error

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.notification.telegram import TelegramNotifier


def verify_bot(token: str) -> dict:
    url = f"https://api.telegram.org/bot{token}/getMe"
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=5) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as e:
        err_body = e.read().decode()
        return {"ok": False, "error": f"HTTP {e.code}: {err_body}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


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
        with urllib.request.urlopen(req, timeout=8) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as e:
        err_body = e.read().decode()
        return {"ok": False, "error": f"HTTP {e.code}: {err_body}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def main():
    parser = argparse.ArgumentParser(description="Test Telegram Bot Incident Notifications")
    parser.add_argument("--token", default=os.getenv("TELEGRAM_BOT_TOKEN"), help="Telegram Bot Token")
    parser.add_argument("--chat-id", default=os.getenv("TELEGRAM_CHAT_ID"), help="Telegram Chat ID or Group ID")
    parser.add_argument("--grafana-url", default="http://localhost:30300", help="Grafana Web URL")
    args = parser.parse_args()

    print("=================================================================")
    print("🤖 TELEGRAM BOT NOTIFICATION TEST")
    print("=================================================================\n")

    if not args.token:
        print("❌ Lỗi: Thiếu Telegram Bot Token!")
        print("👉 Vui lòng truyền: --token <YOUR_TOKEN> hoặc gán export TELEGRAM_BOT_TOKEN='...'")
        print("💡 Hướng dẫn tạo bot: Mở Telegram chat với @BotFather và gõ /newbot")
        sys.exit(1)

    if not args.chat_id:
        print("❌ Lỗi: Thiếu Telegram Chat ID!")
        print("👉 Vui lòng truyền: --chat-id <YOUR_CHAT_ID> hoặc gán export TELEGRAM_CHAT_ID='...'")
        print("💡 Hướng dẫn lấy Chat ID: Nhắn tin cho bot @userinfobot hoặc @RawDataBot trên Telegram.")
        sys.exit(1)

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
    notifier = TelegramNotifier()
    msg = notifier.build_message(
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
        print("      👉 Bạn cần ấn 'START' trò chuyện với Bot trên Telegram trước khi bot có thể gửi tin cho bạn.")
        print("   2. 'group chat was migrated':")
        print("      👉 Nếu gửi vào nhóm, hãy kiểm tra bot đã được thêm vào nhóm và cấp quyền admin/send messages.")

    print("\n=================================================================")


if __name__ == "__main__":
    main()
