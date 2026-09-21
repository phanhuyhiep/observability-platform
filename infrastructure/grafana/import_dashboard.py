"""Utility script to import the Incident Intelligence & RCA dashboard into Grafana automatically.

Usage:
  python3 import_dashboard.py [--url http://localhost:30300] [--user admin] [--password observability2026]
"""

import argparse
import json
import os
import sys
import urllib.request
import urllib.error

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


def main():
    parser = argparse.ArgumentParser(description="Import Incident Dashboard to Grafana")
    parser.add_argument("--url", default=os.getenv("GRAFANA_URL", "http://localhost:30300"), help="Grafana URL")
    parser.add_argument("--user", default=os.getenv("GRAFANA_USER", "admin"), help="Grafana Admin Username")
    parser.add_argument("--password", default=os.getenv("GRAFANA_PASSWORD", "observability2026"), help="Grafana Admin Password")
    args = parser.parse_args()

    dashboard_file = os.path.join(os.path.dirname(__file__), "dashboards", "incident-intelligence-dashboard.json")
    if not os.path.exists(dashboard_file):
        print(f"❌ Không tìm thấy file dashboard: {dashboard_file}")
        sys.exit(1)

    with open(dashboard_file, "r", encoding="utf-8") as f:
        dashboard_json = json.load(f)

    payload = {
        "dashboard": dashboard_json,
        "overwrite": True,
        "message": "Provisioned Incident Intelligence & RCA Dashboard",
    }

    base_url = args.url.rstrip("/")
    api_url = f"{base_url}/api/dashboards/db"

    # Basic Auth
    import base64
    auth_str = f"{args.user}:{args.password}"
    auth_bytes = base64.b64encode(auth_str.encode("utf-8")).decode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Basic {auth_bytes}",
    }

    # Step 1: Ensure PostgreSQL Datasource exists
    ds_url = f"{base_url}/api/datasources"
    ds_payload = {
        "name": "PostgreSQL",
        "type": "postgres",
        "uid": "postgres",
        "url": "detection-postgres.observability.svc.cluster.local:5432",
        "user": "detection",
        "secureJsonData": {
            "password": "detection2026",
        },
        "jsonData": {
            "database": "detection_db",
            "sslmode": "disable",
            "maxOpenConns": 5,
            "maxIdleConns": 2,
        },
    }

    print(f"🔌 [1/2] Đang kiểm tra / cấu hình PostgreSQL Datasource trong Grafana...")
    try:
        req_ds = urllib.request.Request(ds_url, data=json.dumps(ds_payload).encode("utf-8"), headers=headers)
        with urllib.request.urlopen(req_ds, timeout=5) as resp:
            print("   ✅ Đã khởi tạo PostgreSQL datasource thành công!")
    except urllib.error.HTTPError as e:
        if e.code in (409, 400):
            print("   ℹ️ PostgreSQL datasource đã tồn tại sẵn trong Grafana.")
        else:
            print(f"   ⚠️ Lỗi tạo datasource ({e.code}): {e.read().decode('utf-8')}")
    except Exception as e:
        print(f"   ⚠️ Không thể kết nối tạo datasource: {e}")

    # Step 2: Import Dashboard
    print(f"🚀 [2/2] Đang import dashboard vào Grafana tại {base_url}...")
    try:
        req = urllib.request.Request(api_url, data=json.dumps(payload).encode("utf-8"), headers=headers)
        with urllib.request.urlopen(req, timeout=10) as response:
            res_data = json.loads(response.read().decode("utf-8"))
            if res_data.get("status") == "success":
                slug_url = f"{base_url}{res_data.get('url', '')}"
                print("   ✅ IMPORT DASHBOARD THÀNH CÔNG!")
                print(f"   📊 Xem dashboard tại: {slug_url}")
                print(f"   🔗 UID: {res_data.get('uid')}")
            else:
                print(f"   ⚠️ Phản hồi từ Grafana: {res_data}")
    except urllib.error.HTTPError as e:
        err_msg = e.read().decode("utf-8")
        print(f"❌ Lỗi HTTP {e.code}: {err_msg}")
        print("💡 Kiểm tra xem Grafana đã chạy chưa và mật khẩu admin có đúng không.")
    except Exception as e:
        print(f"❌ Lỗi kết nối tới Grafana: {e}")
        print("💡 Hãy chạy port-forward trước: kubectl port-forward svc/grafana 30300:80 -n observability")


if __name__ == "__main__":
    main()
