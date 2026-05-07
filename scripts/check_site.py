import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

# Supabase config
SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://txekjbiathutfhxfzkhd.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
MONITOR_URL = os.environ.get("MONITOR_URL", "https://online.vtu.ac.in/")
STATE_FILE_PATH = os.environ.get("STATE_FILE", "state/site-status.json")


def supabase_request(table: str, method: str = "GET", data: dict = None, filters: dict = None) -> dict:
    """Make a request to Supabase REST API."""
    if not SUPABASE_KEY:
        return {}
    
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    
    if filters:
        filter_str = "".join([f"&{k}=eq.{v}" for k, v in filters.items()])
        url += f"?{filter_str.lstrip('&')}"
    
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }
    
    if method == "GET":
        request_obj = urllib.request.Request(url, headers=headers, method="GET")
    elif method == "POST":
        body = json.dumps(data).encode("utf-8")
        request_obj = urllib.request.Request(url, data=body, headers=headers, method="POST")
    elif method == "PATCH":
        body = json.dumps(data).encode("utf-8")
        url += f"?url=eq.{urllib.parse.quote(MONITOR_URL)}"
        request_obj = urllib.request.Request(url, data=body, headers=headers, method="PATCH")
    
    try:
        with urllib.request.urlopen(request_obj, timeout=15) as response:
            result = response.read().decode("utf-8")
            return json.loads(result) if result else {}
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8")
        print(f"ERROR: Supabase API error {e.code}: {error_body}", file=sys.stderr)
        return {}
    except Exception as e:
        print(f"ERROR: Supabase request failed: {e}", file=sys.stderr)
        return {}


def get_previous_status() -> tuple[str, str, bool]:
    """Get previous status, telegram username, and voice alerts enabled."""
    if SUPABASE_KEY:
        result = supabase_request("monitor_status", filters={"url": MONITOR_URL})
        if isinstance(result, list) and len(result) > 0:
            return (
                result[0].get("status", "unknown"),
                result[0].get("telegram_username", ""),
                result[0].get("voice_alerts_enabled", False)
            )
            
    try:
        if os.path.exists(STATE_FILE_PATH):
            with open(STATE_FILE_PATH, "r") as f:
                data = json.load(f)
                return (
                    data.get("last_status", "unknown"),
                    data.get("telegram_username", ""),
                    data.get("voice_alerts_enabled", False)
                )
    except Exception:
        pass
    return "unknown", "", False


def save_status(status: str, reason: str, checked_at: int) -> None:
    """Save current status."""
    data = {
        "url": MONITOR_URL,
        "status": status,
        "reason": reason,
        "last_checked": checked_at,
    }
    
    try:
        os.makedirs(os.path.dirname(STATE_FILE_PATH), exist_ok=True)
        with open(STATE_FILE_PATH, "w") as f:
            json.dump({"last_status": status, "checked_at": checked_at}, f, indent=2)
    except Exception as e:
        print(f"Warning: Local state write failed: {e}", file=sys.stderr)

    if SUPABASE_KEY:
        result = supabase_request("monitor_status", method="PATCH", data=data)
        if not result or (isinstance(result, list) and len(result) == 0):
            supabase_request("monitor_status", method="POST", data=data)


def save_history(status: str, reason: str, checked_at: int, latency: int) -> None:
    """Save check history."""
    if SUPABASE_KEY:
        data = {
            "url": MONITOR_URL,
            "status": status,
            "reason": reason,
            "checked_at": checked_at,
            "latency": latency
        }
        supabase_request("check_history", method="POST", data=data)


def trigger_voice_call(username: str, site_name: str) -> None:
    """Trigger free voice call alert via CallMeBot."""
    if not username:
        return
    text_message = f"Alert! The website {site_name} status has changed."
    encoded_text = urllib.parse.quote_plus(text_message)
    api_url = f"https://api.callmebot.com/start.php?user={username}&text={encoded_text}&lang=en-US-Standard-B"
    
    try:
        request_obj = urllib.request.Request(api_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(request_obj, timeout=12) as response:
            response.read()
        print("CallMeBot voice alert triggered successfully")
    except Exception as e:
        print(f"Warning: Could not trigger voice call alert: {e}", file=sys.stderr)


def trigger_text_alert(username: str, site_name: str, status: str) -> None:
    """Trigger free high-priority direct text alert via CallMeBot."""
    if not username:
        return
    text_message = f"URGENT: The website {site_name} has changed status to {status.upper()}!"
    encoded_text = urllib.parse.quote_plus(text_message)
    api_url = f"https://api.callmebot.com/text.php?user={username}&text={encoded_text}"
    
    try:
        request_obj = urllib.request.Request(api_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(request_obj, timeout=12) as response:
            response.read()
        print("CallMeBot high-priority direct text alert triggered successfully")
    except Exception as e:
        print(f"Warning: Could not trigger direct text alert: {e}", file=sys.stderr)


def site_is_up(url: str, expected_substring: str) -> tuple[bool, str, int]:
    """Perform HTTP check, return (is_up, reason, response_time_ms)."""
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) WebsiteMonitor/2.0",
        },
    )

    start_time = time.time()
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            body = response.read().decode("utf-8", errors="ignore")
            status_code = getattr(response, "status", response.getcode())
            latency = int((time.time() - start_time) * 1000)
    except urllib.error.HTTPError as error:
        latency = int((time.time() - start_time) * 1000)
        return False, f"http_error_{error.code}", latency
    except urllib.error.URLError as error:
        latency = int((time.time() - start_time) * 1000)
        return False, f"url_error_{error.reason}", latency
    except Exception as e:
        latency = int((time.time() - start_time) * 1000)
        return False, f"network_error_{str(e)[:40]}", latency

    if status_code < 200 or status_code >= 400:
        return False, f"http_status_{status_code}", latency

    if expected_substring and expected_substring not in body:
        return False, "missing_expected_text", latency

    return True, f"http_status_{status_code}", latency


def send_telegram_message(token: str, chat_id: str, message: str, is_alert: bool = False) -> None:
    api_url = f"https://api.telegram.org/bot{token}/sendMessage"
    
    if is_alert:
        alert_payload = urllib.parse.urlencode(
            {
                "chat_id": chat_id,
                "text": "🔔 <b>ALERT!</b> Website status changed!",
                "parse_mode": "HTML",
            }
        ).encode("utf-8")
        request = urllib.request.Request(api_url, data=alert_payload, method="POST")
        request.add_header("Content-Type", "application/x-www-form-urlencoded")
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                response.read()
        except Exception as e:
            print(f"Warning: Could not send alert notification: {e}", file=sys.stderr)
    
    payload = urllib.parse.urlencode(
        {
            "chat_id": chat_id,
            "text": message,
            "disable_web_page_preview": "true",
            "parse_mode": "HTML",
        }
    ).encode("utf-8")

    request = urllib.request.Request(api_url, data=payload, method="POST")
    request.add_header("Content-Type", "application/x-www-form-urlencoded")

    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            response.read()
    except Exception as e:
        print(f"Warning: Could not send detailed Telegram message: {e}", file=sys.stderr)


def main() -> int:
    url = MONITOR_URL
    telegram_token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    telegram_chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    expected_substring = os.environ.get("EXPECTED_SUBSTRING", "").strip()

    if not url:
        print(json.dumps({"error": "MONITOR_URL is required"}), file=sys.stderr)
        return 2

    previous_status, tg_username, voice_enabled = get_previous_status()
    is_up, reason, latency = site_is_up(url, expected_substring)
    current_status = "up" if is_up else "down"
    checked_at = int(time.time())

    print(
        json.dumps(
            {
                "url": url,
                "previous_status": previous_status,
                "current_status": current_status,
                "reason": reason,
                "latency_ms": latency,
                "checked_at": checked_at,
            }
        )
    )

    save_status(current_status, reason, checked_at)
    save_history(current_status, reason, checked_at, latency)

    # State transition alert trigger
    if previous_status != "unknown" and previous_status != current_status:
        # 1. Telegram Message Alert
        if telegram_token and telegram_chat_id:
            status_symbol = "✅" if current_status == "up" else "❌"
            message = (
                f"<b>{status_symbol} Website status changed to {current_status.upper()}!</b>\n\n"
                f"<b>URL:</b> {url}\n"
                f"<b>Previous status:</b> {previous_status}\n"
                f"<b>Reason:</b> {reason}\n"
                f"<b>Latency:</b> {latency}ms\n\n"
                f"<i>Checked at: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(checked_at))}</i>"
            )
            send_telegram_message(telegram_token, telegram_chat_id, message, is_alert=True)
            print("Telegram alert sent")
            
        # 2. CallMeBot Alerts (Always triggers direct Text alert + attempts Voice calling)
        if tg_username:
            # Trigger 100% reliable direct text message
            trigger_text_alert(tg_username, url.split('/')[2], current_status)
            
            # Attempt Voice calling if enabled
            if voice_enabled:
                trigger_voice_call(tg_username, url.split('/')[2])
            
    return 0


if __name__ == "__main__":
    raise SystemExit(main())