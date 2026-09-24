"""
Shared logic: given raw text from a bank SMS or email, decide if it's a
₹2000 CREDIT alert, and if so match it to the oldest pending user within
a time window (FIFO), mark them paid, and notify them via Telegram.

IMPORTANT LIMITATIONS (read before relying on this in production):
- This matches by amount + "credit" keywords only. If two people pay
  ₹2000 within the same MATCH_WINDOW_SECONDS, the FIFO match can assign
  the wrong payment to the wrong user. Keep /pending and /approve as a
  manual audit/override — check match_detail against your actual bank
  statement periodically.
- Bank SMS/email formats vary wildly. The regexes below cover common
  patterns (HDFC, ICICI, SBI, Axis, Google Pay/PhonePe style alerts) but
  you WILL likely need to tune AMOUNT_RE / CREDIT_KEYWORDS / DEBIT_KEYWORDS
  for your specific bank. Log a few real alerts and adjust.
"""
import os
import re
import time
import logging
import requests
from dotenv import load_dotenv

import db

load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHANNEL_ID = os.getenv("PRIVATE_CHANNEL_ID")
TARGET_AMOUNT = 2000
MATCH_WINDOW_SECONDS = int(os.getenv("MATCH_WINDOW_SECONDS", "1800"))  # 30 min

AMOUNT_RE = re.compile(r"(?:INR|Rs\.?|₹)\s?([\d,]+(?:\.\d{1,2})?)", re.IGNORECASE)
CREDIT_KEYWORDS = ["credited", "credit alert", "received", "deposited", "is credited"]
DEBIT_KEYWORDS = ["debited", "debit alert", "spent", "withdrawn", "sent to", "paid to"]

logging.basicConfig(level=logging.INFO)


def _extract_amount(text: str) -> float | None:
    m = AMOUNT_RE.search(text)
    if not m:
        return None
    raw = m.group(1).replace(",", "")
    try:
        return float(raw)
    except ValueError:
        return None


def _looks_like_credit(text_lower: str) -> bool:
    if any(k in text_lower for k in DEBIT_KEYWORDS):
        return False
    return any(k in text_lower for k in CREDIT_KEYWORDS)


def _notify_telegram(telegram_id: int, text: str):
    try:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={"chat_id": telegram_id, "text": text},
            timeout=10,
        )
    except Exception:
        logging.exception("Failed to notify user %s", telegram_id)


def _invite_to_channel(telegram_id: int):
    if not CHANNEL_ID:
        return
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/createChatInviteLink",
            json={"chat_id": CHANNEL_ID, "member_limit": 1, "name": f"paid_{telegram_id}"},
            timeout=10,
        )
        link = r.json().get("result", {}).get("invite_link")
        if link:
            _notify_telegram(telegram_id, f"🎉 Payment confirmed! Join here: {link}")
    except Exception:
        logging.exception("Failed to create invite for %s", telegram_id)


def process_alert_text(raw_text: str, source: str) -> dict:
    """
    source: 'email' or 'sms'. Returns a dict describing what happened,
    useful for logging/debugging.
    """
    text_lower = raw_text.lower()

    if not _looks_like_credit(text_lower):
        return {"matched": False, "reason": "not a credit alert"}

    amount = _extract_amount(raw_text)
    if amount is None:
        return {"matched": False, "reason": "no amount found"}

    if amount != TARGET_AMOUNT:
        return {"matched": False, "reason": f"amount {amount} != {TARGET_AMOUNT}"}

    pending = db.get_pending_oldest_first()
    now = int(time.time())
    pending_in_window = [
        p for p in pending if now - p["requested_at"] <= MATCH_WINDOW_SECONDS
    ]

    if not pending_in_window:
        return {"matched": False, "reason": "no pending user within match window"}

    # FIFO: oldest pending request gets this credit.
    match = pending_in_window[0]
    telegram_id = match["telegram_id"]

    db.mark_paid(telegram_id, matched_by=source, match_detail=raw_text)
    _notify_telegram(
        telegram_id,
        "✅ ₹2000 payment detected and confirmed — you now have full access "
        "to UPPCS Prelims prep.",
    )
    _invite_to_channel(telegram_id)

    logging.info("Matched %s alert to telegram_id=%s", source, telegram_id)
    return {"matched": True, "telegram_id": telegram_id, "source": source}
