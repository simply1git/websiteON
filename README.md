# Website monitor

This repository monitors https://online.vtu.ac.in/ on a GitHub Actions schedule and sends a Telegram message when the site becomes reachable again.

## How it works

- GitHub Actions runs every 5 minutes.
- `scripts/check_site.py` checks the site and stores the last known status in `state/site-status.json`.
- When the site changes from `down` to `up`, the workflow sends a Telegram alert and commits the updated state back to git.

## Required GitHub secrets

Add these repository secrets:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

Optional:

- `EXPECTED_SUBSTRING` to require a specific text fragment in the page before treating it as up.

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