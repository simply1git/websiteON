import json
import os
import subprocess
import time
from datetime import datetime
from pathlib import Path
from flask import Flask, jsonify, render_template, request

app = Flask(__name__)

STATE_FILE = Path(os.getenv("STATE_FILE", "state/site-status.json"))
MONITOR_URL = os.getenv("MONITOR_URL", "https://online.vtu.ac.in/")
CONFIG_FILE = Path("config/monitor.json")


def load_state():
    """Load current monitoring state."""
    if not STATE_FILE.exists():
        return {"last_status": "unknown", "checked_at": 0}
    try:
        return json.loads(STATE_FILE.read_text())
    except:
        return {"last_status": "unknown", "checked_at": 0}


def load_config():
    """Load monitoring configuration."""
    if not CONFIG_FILE.exists():
        return {"monitor_url": MONITOR_URL, "alert_enabled": True}
    try:
        return json.loads(CONFIG_FILE.read_text())
    except:
        return {"monitor_url": MONITOR_URL, "alert_enabled": True}


def save_config(config):
    """Save monitoring configuration."""
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(config, indent=2))


def format_time(timestamp):
    """Format timestamp to readable format."""
    if timestamp == 0:
        return "Never"
    return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")


@app.route("/")
def dashboard():
    """Render monitoring dashboard."""
    state = load_state()
    config = load_config()
    return render_template(
        "index.html",
        status=state["last_status"],
        last_checked=format_time(state["checked_at"]),
        last_checked_timestamp=state["checked_at"],
        monitor_url=config["monitor_url"],
        alert_enabled=config["alert_enabled"],
    )


@app.route("/api/status", methods=["GET"])
def get_status():
    """Get current monitoring status."""
    state = load_state()
    config = load_config()
    return jsonify(
        {
            "status": state["last_status"],
            "last_checked": state["checked_at"],
            "last_checked_formatted": format_time(state["checked_at"]),
            "monitor_url": config["monitor_url"],
            "alert_enabled": config["alert_enabled"],
        }
    )


@app.route("/api/config", methods=["GET", "POST"])
def config_endpoint():
    """Get or update monitoring configuration."""
    if request.method == "POST":
        data = request.get_json()
        config = load_config()
        config.update(data)
        save_config(config)
        
        # Update environment variable for next check
        os.environ["MONITOR_URL"] = config["monitor_url"]
        
        return jsonify({"success": True, "config": config})
    
    config = load_config()
    return jsonify(config)


@app.route("/api/check", methods=["POST"])
def trigger_check():
    """Manually trigger a website check."""
    try:
        config = load_config()
        os.environ["MONITOR_URL"] = config["monitor_url"]
        os.environ["STATE_FILE"] = str(STATE_FILE)
        
        # Run the check script
        result = subprocess.run(
            ["python", "scripts/check_site.py"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        
        state = load_state()
        return jsonify(
            {
                "success": result.returncode == 0,
                "status": state["last_status"],
                "last_checked": state["checked_at"],
                "output": result.stdout,
                "error": result.stderr if result.returncode != 0 else None,
            }
        )
    except subprocess.TimeoutExpired:
        return jsonify({"success": False, "error": "Check timed out"}), 504
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/history", methods=["GET"])
def get_history():
    """Get recent check history."""
    state = load_state()
    history_file = Path("state/history.json")
    
    if history_file.exists():
        try:
            history = json.loads(history_file.read_text())
            return jsonify(history)
        except:
            pass
    
    # Return current state if no history
    return jsonify(
        [
            {
                "status": state["last_status"],
                "timestamp": state["checked_at"],
                "formatted_time": format_time(state["checked_at"]),
            }
        ]
    )


if __name__ == "__main__":
    print("🚀 Starting Website Monitor Dashboard at http://localhost:5000")
    print("📊 Open your browser to view the monitoring dashboard")
    app.run(debug=False, host="0.0.0.0", port=5000)
