import json
import os
import subprocess
import time
from datetime import datetime
from pathlib import Path
from flask import Flask, jsonify, render_template, request, Response

app = Flask(__name__, template_folder=".", static_folder=".")

STATE_DIR = Path("state")
STATE_DIR.mkdir(parents=True, exist_ok=True)

MONITORS_FILE = STATE_DIR / "monitors.json"
HISTORY_FILE = STATE_DIR / "history.json"


def load_monitors():
    """Load all configured monitors."""
    if not MONITORS_FILE.exists():
        default_monitors = [
            {
                "id": "vtu-internships",
                "name": "VTU Applied Internships",
                "url": "https://vtu.internyet.in/dashboard/student/applied-internships",
                "status": "up",
                "reason": "http_status_200",
                "last_checked": int(time.time()),
                "expected_substring": "",
                "alert_enabled": True,
                "telegram_username": "",
                "voice_alerts_enabled": False
            },
            {
                "id": "vtu-portal",
                "name": "VTU Main Portal",
                "url": "https://online.vtu.ac.in/",
                "status": "up",
                "reason": "http_status_200",
                "last_checked": int(time.time()) - 180,
                "expected_substring": "",
                "alert_enabled": True,
                "telegram_username": "",
                "voice_alerts_enabled": False
            }
        ]
        save_monitors(default_monitors)
        return default_monitors
    try:
        return json.loads(MONITORS_FILE.read_text())
    except Exception:
        return []


def save_monitors(monitors):
    """Save monitors configuration."""
    MONITORS_FILE.write_text(json.dumps(monitors, indent=2))


def load_history(monitor_id=None):
    """Load check history, optionally filtered by monitor_id."""
    if not HISTORY_FILE.exists():
        return []
    try:
        history = json.loads(HISTORY_FILE.read_text())
        if monitor_id:
            return [h for h in history if h.get("monitor_id") == monitor_id]
        return history
    except Exception:
        return []


def save_history(history):
    """Save history logs."""
    HISTORY_FILE.write_text(json.dumps(history, indent=2))


def add_history_record(monitor_id, url, status, latency, status_code, reason):
    """Append a new historical record, keeping only the last 100 logs per monitor."""
    history = load_history()
    new_record = {
        "monitor_id": monitor_id,
        "url": url,
        "status": status,
        "latency": int(latency),
        "status_code": status_code,
        "reason": reason,
        "timestamp": int(time.time()),
        "formatted_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    history.insert(0, new_record)
    
    if len(history) > 500:
        history = history[:500]
        
    save_history(history)
    return new_record


@app.route("/")
def dashboard():
    """Render the single master index.html directly from root."""
    return render_template("index.html")


@app.route("/api/monitors", methods=["GET"])
def get_monitors():
    """Get list of all monitors."""
    return jsonify(load_monitors())


@app.route("/api/monitors", methods=["POST"])
def add_monitor():
    """Add a new website monitor."""
    data = request.get_json() or {}
    name = data.get("name", "").strip()
    url = data.get("url", "").strip()
    expected_substring = data.get("expected_substring", "").strip()
    alert_enabled = bool(data.get("alert_enabled", True))
    telegram_username = data.get("telegram_username", "").strip()
    voice_alerts_enabled = bool(data.get("voice_alerts_enabled", False))
    
    if not name or not url:
        return jsonify({"success": False, "error": "Name and URL are required"}), 400
        
    if not (url.startswith("http://") or url.startswith("https://")):
        return jsonify({"success": False, "error": "URL must start with http:// or https://"}), 400

    monitors = load_monitors()
    
    monitor_id = name.lower().replace(" ", "-")
    base_id = monitor_id
    counter = 1
    while any(m["id"] == monitor_id for m in monitors):
        monitor_id = f"{base_id}-{counter}"
        counter += 1

    new_monitor = {
        "id": monitor_id,
        "name": name,
        "url": url,
        "status": "unknown",
        "reason": "Never checked",
        "last_checked": 0,
        "expected_substring": expected_substring,
        "alert_enabled": alert_enabled,
        "telegram_username": telegram_username,
        "voice_alerts_enabled": voice_alerts_enabled
    }
    
    monitors.append(new_monitor)
    save_monitors(monitors)
    return jsonify({"success": True, "monitor": new_monitor})


@app.route("/api/monitors/<monitor_id>", methods=["DELETE"])
def delete_monitor(monitor_id):
    """Delete a monitor configuration."""
    monitors = load_monitors()
    updated = [m for m in monitors if m["id"] != monitor_id]
    
    if len(updated) == len(monitors):
        return jsonify({"success": False, "error": "Monitor not found"}), 404
        
    save_monitors(updated)
    
    history = load_history()
    history = [h for h in history if h.get("monitor_id") != monitor_id]
    save_history(history)
    
    return jsonify({"success": True})


@app.route("/api/check/<monitor_id>", methods=["POST"])
def trigger_check(monitor_id):
    """Trigger check for a specific monitor."""
    monitors = load_monitors()
    monitor = next((m for m in monitors if m["id"] == monitor_id), None)
    
    if not monitor:
        return jsonify({"success": False, "error": "Monitor not found"}), 404
        
    try:
        env = os.environ.copy()
        env["MONITOR_URL"] = monitor["url"]
        env["EXPECTED_SUBSTRING"] = monitor["expected_substring"]
        env["STATE_FILE"] = str(STATE_DIR / f"{monitor_id}-status.json")
        
        start_time = time.time()
        result = subprocess.run(
            ["python", "scripts/check_site.py"],
            capture_output=True,
            text=True,
            timeout=25,
            env=env
        )
        latency = int((time.time() - start_time) * 1000)
        
        status = "down"
        reason = "execution_failed"
        
        try:
            lines = result.stdout.strip().split("\n")
            for line in reversed(lines):
                if line.strip().startswith("{") and line.strip().endswith("}"):
                    info = json.loads(line)
                    status = info.get("current_status", "down")
                    reason = info.get("reason", "unknown")
                    break
        except Exception:
            if "http_status_" in result.stdout:
                status = "up"
            if result.returncode == 0:
                status = "up"
                reason = "http_status_200"

        monitor["status"] = status
        monitor["reason"] = reason
        monitor["last_checked"] = int(time.time())
        save_monitors(monitors)
        
        if "http_status_" in reason:
            try:
                status_code = int(reason.replace("http_status_", ""))
            except:
                status_code = 200 if status == "up" else 500
        else:
            status_code = 200 if status == "up" else 500
            
        add_history_record(
            monitor_id=monitor_id,
            url=monitor["url"],
            status=status,
            latency=latency,
            status_code=status_code,
            reason=reason
        )
        
        return jsonify({
            "success": True,
            "status": status,
            "latency": latency,
            "reason": reason,
            "output": result.stdout,
            "error": result.stderr if result.returncode != 0 else None
        })
    except subprocess.TimeoutExpired:
        return jsonify({"success": False, "error": "Check timed out"}), 504
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/check_all", methods=["POST"])
def trigger_check_all():
    """Trigger manual checking for all active monitors."""
    monitors = load_monitors()
    results = []
    for m in monitors:
        try:
            env = os.environ.copy()
            env["MONITOR_URL"] = m["url"]
            env["EXPECTED_SUBSTRING"] = m["expected_substring"]
            
            start_time = time.time()
            res = subprocess.run(
                ["python", "scripts/check_site.py"],
                capture_output=True,
                text=True,
                timeout=15,
                env=env
            )
            latency = int((time.time() - start_time) * 1000)
            
            status = "down"
            reason = "failed"
            try:
                info = json.loads(res.stdout.strip().split("\n")[-1])
                status = info.get("current_status", "down")
                reason = info.get("reason", "unknown")
            except:
                status = "up" if res.returncode == 0 else "down"
                reason = "http_status_200" if status == "up" else "error"
                
            m["status"] = status
            m["reason"] = reason
            m["last_checked"] = int(time.time())
            
            status_code = 200 if status == "up" else 500
            if "http_status_" in reason:
                try: status_code = int(reason.replace("http_status_", ""))
                except: pass
                
            add_history_record(m["id"], m["url"], status, latency, status_code, reason)
            results.append({"id": m["id"], "status": status, "latency": latency})
        except Exception as e:
            results.append({"id": m["id"], "status": "down", "error": str(e)})
            
    save_monitors(monitors)
    return jsonify({"success": True, "results": results})


@app.route("/api/history/<monitor_id>", methods=["GET"])
def get_monitor_history(monitor_id):
    """Retrieve history data for a specific monitor."""
    return jsonify(load_history(monitor_id))


@app.route("/api/badge/<monitor_id>", methods=["GET"])
def get_badge(monitor_id):
    """Return a premium, dynamic SVG status shield badge."""
    monitors = load_monitors()
    monitor = next((m for m in monitors if m["id"] == monitor_id), None)
    
    status = "unknown"
    color = "#fbbf24"
    
    if monitor:
        status = monitor["status"]
        if status == "up":
            color = "#10b981"
        elif status == "down":
            color = "#ef4444"
            
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
