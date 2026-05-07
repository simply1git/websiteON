import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


def load_state(state_path: Path) -> str:
    if not state_path.exists():
        return "unknown"

    try:
        data = json.loads(state_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return "unknown"

    return str(data.get("last_status", "unknown"))


def save_state(state_path: Path, status: str, checked_at: int) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "last_status": status,
        "checked_at": checked_at,
    }
    state_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


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


def send_telegram_message(token: str, chat_id: str, message: str) -> None:
    api_url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = urllib.parse.urlencode(
        {
            "chat_id": chat_id,
            "text": message,
            "disable_web_page_preview": "true",
        }
    ).encode("utf-8")

    request = urllib.request.Request(api_url, data=payload, method="POST")
    request.add_header("Content-Type", "application/x-www-form-urlencoded")

    with urllib.request.urlopen(request, timeout=20) as response:
        response.read()


def main() -> int:
    url = os.environ.get("MONITOR_URL", "https://online.vtu.ac.in/").strip()
    state_file = Path(os.environ.get("STATE_FILE", "state/site-status.json"))
    telegram_token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    telegram_chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    expected_substring = os.environ.get("EXPECTED_SUBSTRING", "").strip()

    if not url:
        print("MONITOR_URL is required", file=sys.stderr)
        return 2

    previous_status = load_state(state_file)
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

    if previous_status != current_status and current_status == "up":
        if not telegram_token or not telegram_chat_id:
            print("Telegram secrets are missing, cannot send alert", file=sys.stderr)
            save_state(state_file, current_status, checked_at)
            return 1

        message = (
            f"Website is live again: {url}\n"
            f"Previous status: {previous_status}\n"
            f"Check reason: {reason}"
        )
        send_telegram_message(telegram_token, telegram_chat_id, message)
        print("Telegram alert sent")

    save_state(state_file, current_status, checked_at)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())