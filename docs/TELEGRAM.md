# Telegram road reports

The core demo needs no bot. Its +45-minute button is explicitly a simulation. The optional ingress below accepts operator-supplied route reports; it does not scrape news or claim that a road is safe.

1. Create a bot using Telegram's official BotFather and retain its token privately. The application does not need the bot token for inbound webhook verification.
2. Deploy the Python server behind HTTPS. Set `TELEGRAM_WEBHOOK_SECRET` to a strong random value and `TELEGRAM_CHAT_ID` to the one authorized chat ID using your hosting provider's secure environment settings. Never commit them.
3. Register `https://YOUR_HOST/api/telegram/webhook` with Telegram's official `setWebhook` API, setting its `secret_token` to the same webhook secret and `allowed_updates` to `["message"]`. Use your own trusted administration tool; avoid putting bot-token URLs in shared shell history or logs. Official reference: https://core.telegram.org/bots/api#setwebhook
4. In the authorized chat, send `/delay A 45`. Route A is the seeded Charity A route; the integer can be 0–180 minutes.
5. In the optimized dashboard, open **تقارير الطرق من Telegram**, refresh, review the unverified report, then explicitly apply it. This changes only the current browser's simulated route and triggers ReOPT. It does not dispatch a vehicle.

The webhook checks the Telegram secret header with constant-time comparison, allowlists the chat, enforces structured commands and one-hour freshness, deduplicates by `update_id`, caps body size and deletes stored reports after a day during subsequent ingestion. Only the last hour is shown. The app stores normalized route/delay data, not the raw message or user identity.

A report is not independent confirmation. No model interprets free-form news. No messages are sent by this application. Telegram was tested with authenticated synthetic updates, not an actual configured bot.
