# Website monitor

This repository monitors a website via GitHub Actions (every 5 minutes) and sends **Telegram alerts with notifications** when the site transitions from down to up.

## Features

✅ **Automated monitoring** – GitHub Actions checks every 5 minutes  
✅ **Smart alerts** – Sends Telegram notification + alert message only on down→up transition  
✅ **Web dashboard** – Monitor status and change configuration in your browser  
✅ **Free** – Uses only GitHub Actions and free Telegram Bot API  
✅ **History tracking** – Keeps last 100 check results  

## Quick Start

### 1. Local Setup

```bash
# Install Flask (only dependency for web dashboard)
pip install flask

# Copy .env template
cp .env.example .env  # if available, or create .env with:
# MONITOR_URL=https://your-site.com
# TELEGRAM_BOT_TOKEN=your_token
# TELEGRAM_CHAT_ID=your_chat_id
# STATE_FILE=state/site-status.json

# Run the web dashboard
python app.py
# Open http://localhost:5000
```

### 2. Configure Telegram Bot

1. Message @BotFather on Telegram, run `/newbot`, and follow prompts
2. Copy the bot token
3. Send any message to your new bot
4. Get your chat ID:
   ```bash
   python scripts/get_telegram_chat_id.py <YOUR_BOT_TOKEN>
   ```
5. Add to `.env`:
   ```
   TELEGRAM_BOT_TOKEN=your_token_here
   TELEGRAM_CHAT_ID=your_chat_id_here
   ```

### 3. GitHub Setup (for automated monitoring)

1. Push this repo to GitHub
2. Go to **Settings → Secrets and variables → Actions**
3. Add these secrets:
   - `TELEGRAM_BOT_TOKEN` – from @BotFather
   - `TELEGRAM_CHAT_ID` – from get_telegram_chat_id.py
4. (Optional) `EXPECTED_SUBSTRING` – text that must appear on page

## How it works

- **Locally:** Run `python app.py` to launch the web dashboard (no Flask needed for CLI)
- **GitHub Actions:** Workflow runs `.github/workflows/monitor.yml` every 5 minutes
- **State Persistence:** Last known status stored in `state/site-status.json`
- **Alerts:** Sends Telegram message with 🔔 alert notification + detailed info
- **History:** Last 100 checks logged in `state/history.json`

## Web Dashboard

Visit `http://localhost:5000` to:
- View current site status
- Manually trigger a check
- Change the monitored URL
- Enable/disable alerts
- See last check time

## Telegram Alerts

Alerts include:
- 🔔 Urgent notification message
- ✅ Detailed status with timestamp
- Previous status and check reason

Messages go to: https://t.me/websiteON_bot (or your custom bot)

## Configuration

Edit `config/monitor.json` or use the web dashboard to change:
- `monitor_url` – which site to monitor
- `alert_enabled` – toggle Telegram alerts

## Required GitHub secrets

Add these repository secrets:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `SUPABASE_SERVICE_ROLE_KEY`

Optional:

- `EXPECTED_SUBSTRING` to require a specific text fragment in the page before treating it as up.

The public dashboard uses the Supabase anon key for read access only. The GitHub Actions workflow must use the service-role key so it can write `monitor_status` and `check_history` rows while RLS stays enabled.

## Telegram setup

1. Create a bot with @BotFather on Telegram and copy the bot token.
2. Run the chat ID helper to get your chat ID:
   ```
   python scripts/get_telegram_chat_id.py <YOUR_BOT_TOKEN>
   ```
3. Send any message to your bot in Telegram—your chat ID will be printed.
4. Add the token and chat ID to your GitHub repository secrets:
   - `TELEGRAM_BOT_TOKEN`: the token from BotFather
   - `TELEGRAM_CHAT_ID`: the ID from the helper script

## Notes

- This is free aside from GitHub Actions usage limits.
- GitHub scheduled workflows run at least every 5 minutes and can be delayed under load.
- If you want a true always-on monitor later, move the same script to a VPS or always-on machine.