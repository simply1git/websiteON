import json
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


def supabase_request(table: str, method: str = "GET", data: dict = None, filters: dict = None) -> dict:
    """Make a request to Supabase REST API."""
    if not SUPABASE_KEY:
        print("ERROR: SUPABASE_KEY not set")
        return {}
    
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    
    # Add filters to URL
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
        with urllib.request.urlopen(request_obj, timeout=20) as response:
            result = response.read().decode("utf-8")
            return json.loads(result) if result else {}
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8")
        print(f"ERROR: Supabase API error {e.code}: {error_body}", file=sys.stderr)
        return {}
    except Exception as e:
        print(f"ERROR: Supabase request failed: {e}", file=sys.stderr)
        return {}


def get_previous_status() -> str:
    """Get previous status from Supabase."""
    result = supabase_request("monitor_status", filters={"url": MONITOR_URL})
    
    if isinstance(result, list) and len(result) > 0:
        return result[0].get("status", "unknown")
    return "unknown"


def save_status(status: str, reason: str, checked_at: int) -> None:
    """Save current status to Supabase."""
    data = {
        "url": MONITOR_URL,
        "status": status,
        "reason": reason,
        "last_checked": checked_at,
    }
    
    # Try PATCH first (update existing)
    result = supabase_request("monitor_status", method="PATCH", data=data)
    
    # If no rows returned, insert new
    if not result or (isinstance(result, list) and len(result) == 0):
        supabase_request("monitor_status", method="POST", data=data)


def save_history(status: str, reason: str, checked_at: int) -> None:
    """Save to check history in Supabase."""
    data = {
        "url": MONITOR_URL,
        "status": status,
        "reason": reason,
        "checked_at": checked_at,
    }
    supabase_request("check_history", method="POST", data=data)

def site_is_up(url: str, expected_substring: str) -> tuple[bool, str]:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (website-monitor)",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            body = response.read().decode("utf-8", errors="ignore")
            status_code = getattr(response, "status", response.getcode())
    except urllib.error.HTTPError as error:
        return False, f"http_error_{error.code}"
    except urllib.error.URLError as error:
        return False, f"url_error_{error.reason}"

    if status_code < 200 or status_code >= 400:
        return False, f"http_status_{status_code}"

    if expected_substring and expected_substring not in body:
        return False, "missing_expected_text"

    return True, f"http_status_{status_code}"


def send_telegram_message(token: str, chat_id: str, message: str, is_alert: bool = False) -> None:
    api_url = f"https://api.telegram.org/bot{token}/sendMessage"
    
    # Send urgent alert notification first
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
            with urllib.request.urlopen(request, timeout=20) as response:
                response.read()
        except Exception as e:
            print(f"Warning: Could not send alert notification: {e}")
    
    # Send detailed message
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

    with urllib.request.urlopen(request, timeout=20) as response:
        response.read()


def main() -> int:
    url = MONITOR_URL
    telegram_token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    telegram_chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    expected_substring = os.environ.get("EXPECTED_SUBSTRING", "").strip()

    if not url:
        print("MONITOR_URL is required", file=sys.stderr)
        return 2

    if not SUPABASE_KEY:
        print("SUPABASE_KEY is required", file=sys.stderr)
        return 2

    previous_status = get_previous_status()
    is_up, reason = site_is_up(url, expected_substring)
    current_status = "up" if is_up else "down"
    checked_at = int(time.time())

    print(
        json.dumps(
            {
                "url": url,
                "previous_status": previous_status,
                "current_status": current_status,
                "reason": reason,
                "checked_at": checked_at,
            }
        )
    )

    # Save status to Supabase
    save_status(current_status, reason, checked_at)
    save_history(current_status, reason, checked_at)

    # Send alert if transitioned from down to up
    if previous_status != current_status and current_status == "up":
        if not telegram_token or not telegram_chat_id:
            print("Telegram secrets are missing, cannot send alert", file=sys.stderr)
            return 1

        message = (
            f"<b>✅ Website is live again!</b>\n\n"
            f"<b>URL:</b> {url}\n"
            f"<b>Previous status:</b> {previous_status}\n"
            f"<b>Reason:</b> {reason}\n\n"
            f"<i>Time checked: {checked_at}</i>"
        )
        send_telegram_message(telegram_token, telegram_chat_id, message, is_alert=True)
        print("Telegram alert sent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())