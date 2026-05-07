import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from flask import Flask, jsonify, render_template, request, Response

app = Flask(__name__, template_folder=".", static_folder=".")

STATE_DIR = Path("state")
STATE_DIR.mkdir(parents=True, exist_ok=True)
MONITORS_FILE = STATE_DIR / "monitors.json"
HISTORY_FILE = STATE_DIR / "history.json"

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://txekjbiathutfhxfzkhd.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()


def supabase_request(table: str, method: str = "GET", data: dict = None, filters: dict = None):
    """Interact with Supabase REST API synchronously."""
    if not SUPABASE_KEY:
        return None
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    if filters:
        filter_str = "".join([f"&{k}=eq.{urllib.parse.quote(v)}" for k, v in filters.items()])
        url += f"?{filter_str.lstrip('&')}"
    
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }
    
    try:
        if method == "GET":
            req = urllib.request.Request(url, headers=headers, method="GET")
        elif method == "POST":
            req = urllib.request.Request(url, data=json.dumps(data).encode("utf-8"), headers=headers, method="POST")
        elif method == "PATCH":
            if data and "url" in data:
                url += f"?url=eq.{urllib.parse.quote(data['url'])}"
            req = urllib.request.Request(url, data=json.dumps(data).encode("utf-8"), headers=headers, method="PATCH")
        elif method == "DELETE":
            req = urllib.request.Request(url, headers=headers, method="DELETE")
            
        with urllib.request.urlopen(req, timeout=10) as response:
            res = response.read().decode("utf-8")
            return json.loads(res) if res else []
    except Exception as e:
        print(f"Supabase API Error ({method}): {e}")
        return None


def load_monitors():
    """Load monitors from Supabase if configured, otherwise local JSON."""
    if SUPABASE_KEY:
        res = supabase_request("monitor_status")
        if res is not None:
            monitors = []
            for r in res:
                monitors.append({
                    "id": r.get("url"),
                    "name": r.get("name", r.get("url", "")),
                    "url": r.get("url", ""),
                    "status": r.get("status", "unknown"),
                    "reason": r.get("reason", "Never checked"),
                    "last_checked": r.get("last_checked", 0),
                    "expected_substring": "",
                    "telegram_username": r.get("telegram_username", ""),
                    "voice_alerts_enabled": r.get("voice_alerts_enabled", False)
                })
            return monitors

    if not MONITORS_FILE.exists():
        return []
    try:
        return json.loads(MONITORS_FILE.read_text())
    except Exception:
        return []


def save_monitor(monitor):
    """Save/Update a single monitor state."""
    if SUPABASE_KEY:
        data = {
            "url": monitor["url"],
            "name": monitor["name"],
            "status": monitor["status"],
            "reason": monitor["reason"],
            "last_checked": monitor["last_checked"],
            "telegram_username": monitor.get("telegram_username", ""),
            "voice_alerts_enabled": monitor.get("voice_alerts_enabled", False)
        }
        res = supabase_request("monitor_status", method="PATCH", data=data)
        if res is None or len(res) == 0:
            supabase_request("monitor_status", method="POST", data=data)
    else:
        monitors = load_monitors()
        updated = False
        for i, m in enumerate(monitors):
            if m["id"] == monitor["id"]:
                monitors[i] = monitor
                updated = True
                break
        if not updated:
            monitors.append(monitor)
        MONITORS_FILE.write_text(json.dumps(monitors, indent=2))


def delete_monitor_data(monitor_id):
    """Remove monitor from datastore."""
    if SUPABASE_KEY:
        supabase_request("monitor_status", method="DELETE", filters={"url": monitor_id})
    else:
        monitors = load_monitors()
        updated = [m for m in monitors if m["id"] != monitor_id]
        MONITORS_FILE.write_text(json.dumps(updated, indent=2))


def add_history_record(monitor_id, url, status, latency, reason):
    """Insert log record."""
    timestamp = int(time.time())
    if SUPABASE_KEY:
        data = {
            "url": url,
            "status": status,
            "reason": reason,
            "checked_at": timestamp,
            "latency": latency
        }
        supabase_request("check_history", method="POST", data=data)
    else:
        if not HISTORY_FILE.exists():
            history = []
        else:
            try: history = json.loads(HISTORY_FILE.read_text())
            except: history = []
            
        history.insert(0, {
            "monitor_id": monitor_id,
            "url": url,
            "status": status,
            "latency": latency,
            "reason": reason,
            "timestamp": timestamp,
            "formatted_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
        history = history[:500]
        HISTORY_FILE.write_text(json.dumps(history, indent=2))


def load_history(monitor_id=None):
    """Load history records."""
    if SUPABASE_KEY:
        filters = {"url": monitor_id} if monitor_id else {}
        res = supabase_request("check_history", filters=filters)
        if res is not None:
            # Map back to local format for frontend compatibility
            logs = []
            for r in res:
                logs.append({
                    "monitor_id": r.get("url"),
                    "url": r.get("url"),
                    "status": r.get("status"),
                    "latency": r.get("latency", 150),
                    "reason": r.get("reason"),
                    "timestamp": r.get("checked_at", 0)
                })
            # Supabase returns them ascending if not ordered, we need descending usually
            logs.sort(key=lambda x: x["timestamp"], reverse=True)
            return logs

    if not HISTORY_FILE.exists():
        return []
    try:
        history = json.loads(HISTORY_FILE.read_text())
        if monitor_id:
            return [h for h in history if h.get("monitor_id") == monitor_id]
        return history
    except Exception:
        return []


# --- ALERTS & CHECKING LOGIC ---

def trigger_text_alert(username: str, site_name: str, status: str) -> None:
    if not username: return
    text_message = f"URGENT: {site_name} changed status to {status.upper()}!"
    url = f"https://api.callmebot.com/text.php?user={urllib.parse.quote(username)}&text={urllib.parse.quote_plus(text_message)}"
    try:
        urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=10)
        print(f"Text alert dispatched for {site_name}")
    except Exception as e:
        print(f"Warning: Text alert failed: {e}")


def trigger_voice_call(username: str, site_name: str) -> None:
    if not username: return
    text_message = f"Alert! {site_name} has changed status."
    url = f"https://api.callmebot.com/start.php?user={urllib.parse.quote(username)}&text={urllib.parse.quote_plus(text_message)}&lang=en-US-Standard-B"
    try:
        urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=10)
        print(f"Voice call dispatched for {site_name}")
    except Exception as e:
        print(f"Warning: Voice call failed: {e}")


def send_telegram_bot_message(message: str) -> None:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID: return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = urllib.parse.urlencode({
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }).encode("utf-8")
    
    try:
        req = urllib.request.Request(url, data=payload, method="POST")
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        print(f"Telegram Bot Message Failed: {e}")


def perform_http_check(url: str, expected_substring: str) -> tuple[str, str, int]:
    """Synchronously checks if website is up and returns status, reason, latency."""
    request_obj = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 WebsiteMonitor/2.0"})
    start_time = time.time()
    try:
        with urllib.request.urlopen(request_obj, timeout=12) as response:
            body = response.read().decode("utf-8", errors="ignore")
            status_code = getattr(response, "status", response.getcode())
            latency = int((time.time() - start_time) * 1000)
            
            if status_code < 200 or status_code >= 400:
                return "down", f"http_status_{status_code}", latency
            if expected_substring and expected_substring not in body:
                return "down", "missing_expected_text", latency
            
            return "up", f"http_status_{status_code}", latency
            
    except urllib.error.HTTPError as error:
        return "down", f"http_error_{error.code}", int((time.time() - start_time) * 1000)
    except urllib.error.URLError as error:
        return "down", f"url_error_{error.reason}", int((time.time() - start_time) * 1000)
    except Exception as e:
        return "down", f"network_error_{str(e)[:40]}", int((time.time() - start_time) * 1000)


def process_monitor_check(m: dict) -> dict:
    previous_status = m["status"]
    url = m["url"]
    
    status, reason, latency = perform_http_check(url, m.get("expected_substring", ""))
    m["status"] = status
    m["reason"] = reason
    m["last_checked"] = int(time.time())
    
    save_monitor(m)
    add_history_record(m["id"], url, status, latency, reason)
    
    # State Transition Detected!
    if previous_status != "unknown" and previous_status != status:
        print(f"STATE CHANGE DETECTED FOR {url}: {previous_status} -> {status}")
        
        status_symbol = "✅" if status == "up" else "❌"
        msg = f"<b>{status_symbol} {m['name']} changed to {status.upper()}!</b>\nReason: {reason}\nLatency: {latency}ms"
        send_telegram_bot_message(msg)
        
        tg_username = m.get("telegram_username", "").strip()
        if tg_username:
            trigger_text_alert(tg_username, m["name"], status)
            if m.get("voice_alerts_enabled"):
                trigger_voice_call(tg_username, m["name"])
                
    return {"id": m["id"], "status": status, "latency": latency, "reason": reason}


# --- API ROUTES ---

@app.route("/")
def dashboard():
    return render_template("index.html")


@app.route("/api/monitors", methods=["GET"])
def get_monitors():
    return jsonify(load_monitors())


@app.route("/api/monitors", methods=["POST"])
def add_monitor():
    data = request.get_json() or {}
    name = data.get("name", "").strip()
    url = data.get("url", "").strip()
    expected_substring = data.get("expected_substring", "").strip()
    telegram_username = data.get("telegram_username", "").strip()
    voice_alerts_enabled = bool(data.get("voice_alerts_enabled", False))
    
    if not name or not url:
        return jsonify({"success": False, "error": "Name and URL are required"}), 400

    new_monitor = {
        "id": url, # using URL as universal ID to align local with Supabase Schema
        "name": name,
        "url": url,
        "status": "unknown",
        "reason": "Never checked",
        "last_checked": 0,
        "expected_substring": expected_substring,
        "telegram_username": telegram_username,
        "voice_alerts_enabled": voice_alerts_enabled
    }
    save_monitor(new_monitor)
    return jsonify({"success": True, "monitor": new_monitor})


@app.route("/api/monitors/<path:monitor_id>", methods=["DELETE"])
def delete_monitor_api(monitor_id):
    # Monitor ID is URL due to cloud schema, so parse properly
    delete_monitor_data(monitor_id)
    return jsonify({"success": True})


@app.route("/api/check/<path:monitor_id>", methods=["POST"])
def trigger_check_api(monitor_id):
    monitors = load_monitors()
    monitor = next((m for m in monitors if m["id"] == monitor_id), None)
    if not monitor:
        return jsonify({"success": False, "error": "Monitor not found"}), 404
        
    res = process_monitor_check(monitor)
    return jsonify({"success": True, "status": res["status"], "latency": res["latency"], "reason": res["reason"]})


@app.route("/api/check_all", methods=["GET", "POST"])
def trigger_check_all():
    """Executed by Vercel Cron or local check."""
    monitors = load_monitors()
    results = []
    for m in monitors:
        results.append(process_monitor_check(m))
    return jsonify({"success": True, "results": results})


@app.route("/api/test_alerts/<path:monitor_id>", methods=["POST"])
def test_alerts(monitor_id):
    monitors = load_monitors()
    monitor = next((m for m in monitors if m["id"] == monitor_id), None)
    if not monitor:
        return jsonify({"success": False, "error": "Monitor not found"}), 404
    
    tg_user = monitor.get("telegram_username", "").strip()
    output = []
    
    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        send_telegram_bot_message(f"<b>🔔 Test Alert</b>\nEverything is working correctly for <b>{monitor['name']}</b>!")
        output.append("Telegram text message successfully sent")
            
    if tg_user:
        trigger_text_alert(tg_user, monitor["name"], "UP")
        output.append("CallMeBot Direct Text Alert dispatched")
        if monitor.get("voice_alerts_enabled"):
            trigger_voice_call(tg_user, monitor["name"])
            output.append("Telegram phone call dispatched")
            
    return jsonify({"success": True, "output": output})


@app.route("/api/history/<path:monitor_id>", methods=["GET"])
def get_monitor_history(monitor_id):
    return jsonify(load_history(monitor_id))


@app.route("/api/badge/<path:monitor_id>", methods=["GET"])
def get_badge(monitor_id):
    monitors = load_monitors()
    monitor = next((m for m in monitors if m["id"] == monitor_id), None)
    status = monitor["status"] if monitor else "unknown"
    color = "#10b981" if status == "up" else "#ef4444" if status == "down" else "#fbbf24"
            
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="112" height="20">
    <linearGradient id="b" x2="0" y2="100%">
        <stop offset="0" stop-color="#bbb" stop-opacity=".1"/>
        <stop offset="1" stop-opacity=".1"/>
    </linearGradient>
    <mask id="a">
        <rect width="112" height="20" rx="4" fill="#fff"/>
    </mask>
    <g mask="url(#a)">
        <rect width="62" height="20" fill="#1e293b"/>
        <rect x="62" width="50" height="20" fill="{color}"/>
        <rect width="112" height="20" fill="url(#b)"/>
    </g>
    <g fill="#fff" text-anchor="middle" font-family="DejaVu Sans,Verdana,Geneva,sans-serif" font-size="11">
        <text x="32" y="15" fill="#010101" fill-opacity=".3">monitor</text>
        <text x="32" y="14">monitor</text>
        <text x="86" y="15" fill="#010101" fill-opacity=".3">{status}</text>
        <text x="86" y="14">{status}</text>
    </g>
</svg>"""
    return Response(svg, mimetype="image/svg+xml")


if __name__ == "__main__":
    print("🚀 Website Monitor Dashboard starting on http://localhost:5000")
    app.run(debug=True, host="0.0.0.0", port=5000)
