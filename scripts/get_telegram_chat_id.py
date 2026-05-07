#!/usr/bin/env python3
"""
Get your Telegram chat ID.

Usage:
  python scripts/get_telegram_chat_id.py <BOT_TOKEN>

Steps:
  1. Run this script with your bot token.
  2. Send any message to your bot in Telegram.
  3. Your chat ID will be printed to the console.
"""

import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request


def get_updates(token: str, offset: int = 0) -> dict:
    """Fetch pending updates from Telegram."""
    api_url = f"https://api.telegram.org/bot{token}/getUpdates"
    params = urllib.parse.urlencode({"offset": offset, "timeout": 30}).encode("utf-8")
    request = urllib.request.Request(f"{api_url}?{params.decode('utf-8')}")

    try:
        with urllib.request.urlopen(request, timeout=35) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as error:
        print(f"Error connecting to Telegram: {error.reason}", file=sys.stderr)
        return {"ok": False, "result": []}


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python scripts/get_telegram_chat_id.py <BOT_TOKEN>", file=sys.stderr)
        print("", file=sys.stderr)
        print("Get your chat ID:", file=sys.stderr)
        print("  1. Create a bot with @BotFather on Telegram.", file=sys.stderr)
        print("  2. Copy the bot token.", file=sys.stderr)
        print("  3. Run this script with the token as an argument.", file=sys.stderr)
        print("  4. Send any message to your bot in Telegram.", file=sys.stderr)
        print("  5. Your chat ID will appear here.", file=sys.stderr)
        return 2

    token = sys.argv[1].strip()
    if not token:
        print("Bot token cannot be empty", file=sys.stderr)
        return 2

    print("Listening for messages from your Telegram bot...")
    print("Send any message to your bot now.", file=sys.stderr)
    print()

    offset = 0
    checked_count = 0
    while True:
        try:
            data = get_updates(token, offset)
            if not data.get("ok"):
                print(f"Error from Telegram: {data.get('description', 'Unknown error')}", file=sys.stderr)
                time.sleep(2)
                continue

            updates = data.get("result", [])
            if updates:
                for update in updates:
                    if "message" in update and "chat" in update["message"]:
                        chat_id = update["message"]["chat"]["id"]
                        chat_name = update["message"]["chat"].get("username", "")
                        print()
                        print("=" * 50)
                        print("SUCCESS! Your Telegram chat ID is:")
                        print()
                        print(f"  {chat_id}")
                        print()
                        if chat_name:
                            print(f"  (Username: @{chat_name})")
                        print()
                        print("Add this to your GitHub repository secrets as:")
                        print("  TELEGRAM_CHAT_ID")
                        print("=" * 50)
                        return 0

                    offset = update["update_id"] + 1

            checked_count += 1
            if checked_count % 6 == 0:
                print(".", end="", flush=True)

        except KeyboardInterrupt:
            print("\n\nInterrupted.", file=sys.stderr)
            return 1
        except Exception as error:
            print(f"Error: {error}", file=sys.stderr)
            time.sleep(2)


if __name__ == "__main__":
    raise SystemExit(main())
