# UPPCS Prelims — ₹2000 via plain UPI link (no payment gateway)

No Razorpay/Cashfree, no fees to a gateway. The bot generates a real
`upi://pay?...` deep link + QR straight to your own UPI ID (VPA). Users
pay you directly. Because there's no gateway API, **there's no built-in
"payment succeeded" callback** — this bot fills that gap two ways:

1. **Email auto-confirm** (`email_watcher.py`) — polls your inbox via
   IMAP for your bank's credit-alert emails, extracts the amount, and
   matches it to a waiting user.
2. **SMS auto-confirm** (`webhook_server.py`) — receives bank SMS
   forwarded from your phone via a small Android forwarder app, same
   matching logic.
3. **Manual override** (`/approve` in the bot) — always available as a
   safety net / for when auto-detection misses something.

## ⚠️ Read this before relying on it
Matching works by **amount only** (everyone pays exactly ₹2000 to the
same UPI ID) using FIFO — the oldest unpaid `/buy` request within
`MATCH_WINDOW_SECONDS` gets credited. If two people pay ₹2000 within
that window, a payment **can get assigned to the wrong person**. Use
`/pending` to see the queue and `match_detail` in the DB to audit
against your real bank statement. For meaningful volume, a payment
gateway (Razorpay/Cashfree Payment Links) gives you a real reference
number per transaction and removes this ambiguity — worth reconsidering
once you're past a handful of daily sales.

## Setup
1. Copy `.env.example` → `.env`.
2. `UPI_VPA` — your own UPI ID (e.g. `yourname@okhdfcbank`), `PAYEE_NAME`
   — shown in the paying user's UPI app.
3. `TELEGRAM_BOT_TOKEN` from [@BotFather](https://t.me/BotFather).
   `ADMIN_TELEGRAM_IDS` — your own Telegram numeric ID(s), for
   `/pending` and `/approve`. (Get your ID from
   [@userinfobot](https://t.me/userinfobot).)
4. `pip install -r requirements.txt`

### Email auto-confirm (recommended — works from any server)
- Gmail: enable IMAP (Settings → Forwarding and POP/IMAP), then create
  an **App Password** (Google Account → Security → 2-Step Verification
  → App passwords) — don't use your real password.
- Set `IMAP_USER`, `IMAP_APP_PASSWORD`, and `BANK_SENDER_EMAIL` (your
  bank's alert sender address) in `.env`.
- **Tune the parser**: `matcher.py` has `AMOUNT_RE`, `CREDIT_KEYWORDS`,
  `DEBIT_KEYWORDS`. Bank email formats vary a lot — forward yourself a
  couple of real ₹ credit alerts, check what `email_watcher.py` logs,
  and adjust the regex/keywords until it reliably detects them.
- Run: `python email_watcher.py` (keep running via systemd/pm2/screen).

### SMS auto-confirm (optional, needs an Android phone)
- Install an SMS-forwarding app (MacroDroid, Automate, Tasker, or a
  dedicated "SMS to Webhook" app) on a phone that gets your bank's SMS
  alerts.
- Configure it to POST to `https://yourdomain.com/sms/incoming` with
  JSON body `{"sender": "...", "text": "...", "secret": "<SMS_WEBHOOK_SECRET>"}`.
- Run: `python webhook_server.py` (needs a public HTTPS URL — nginx +
  domain, or a tunnel like ngrok/Cloudflare Tunnel for testing).

### Run the bot
```
python bot.py
```

## Commands
- `/start`, `/buy`, `/status` — for users
- `/pending` — admin: list unmatched payment requests
- `/approve <telegram_id>` — admin: manually confirm someone's payment

## Honest tradeoffs vs. a gateway
- ✅ No transaction fees, no KYC/onboarding delay, works with any UPI ID.
- ❌ No cryptographic proof of payment — you're trusting your own
  bank's SMS/email + amount matching.
- ❌ Ambiguous under concurrent payments of the same amount (see above).
- ❌ Refunds, disputes, invoicing are all manual — a gateway automates
  these.
