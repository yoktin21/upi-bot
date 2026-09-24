"""
Polls an inbox (e.g. Gmail) for new bank credit-alert emails and feeds
their text into matcher.process_alert_text().

Setup notes:
- If using Gmail: enable IMAP (Settings -> Forwarding and POP/IMAP) and
  create an "App Password" (Google Account -> Security -> 2-Step
  Verification -> App passwords) — do NOT use your normal password.
- Set SENDER_FILTER to your bank's alert sender address (e.g.
  "alerts@hdfcbank.net") so you don't process unrelated mail.
- This only reads UNSEEN mail and marks it read after processing, so
  restarting the script won't reprocess old alerts.

Run: python email_watcher.py   (keep it running, e.g. via systemd/pm2)
"""
import os
import time
import email
import imaplib
import logging
from email.header import decode_header
from dotenv import load_dotenv

import matcher

load_dotenv()

IMAP_HOST = os.getenv("IMAP_HOST", "imap.gmail.com")
IMAP_USER = os.getenv("IMAP_USER")
IMAP_PASS = os.getenv("IMAP_APP_PASSWORD")
SENDER_FILTER = os.getenv("BANK_SENDER_EMAIL", "")  # e.g. alerts@hdfcbank.net
POLL_SECONDS = int(os.getenv("EMAIL_POLL_SECONDS", "30"))

logging.basicConfig(level=logging.INFO)


def _decode(s):
    if not s:
        return ""
    parts = decode_header(s)
    out = ""
    for text, enc in parts:
        out += text.decode(enc or "utf-8") if isinstance(text, bytes) else text
    return out


def _get_body(msg) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            if ctype == "text/plain":
                try:
                    return part.get_payload(decode=True).decode(errors="ignore")
                except Exception:
                    continue
        # fall back to html if no plain text part
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                try:
                    return part.get_payload(decode=True).decode(errors="ignore")
                except Exception:
                    continue
        return ""
    else:
        try:
            return msg.get_payload(decode=True).decode(errors="ignore")
        except Exception:
            return str(msg.get_payload())


def poll_once():
    conn = imaplib.IMAP4_SSL(IMAP_HOST)
    conn.login(IMAP_USER, IMAP_PASS)
    conn.select("INBOX")

    search_criteria = "UNSEEN"
    if SENDER_FILTER:
        search_criteria = f'(UNSEEN FROM "{SENDER_FILTER}")'

    status, data = conn.search(None, search_criteria)
    if status != "OK":
        conn.logout()
        return

    ids = data[0].split()
    for eid in ids:
        status, msg_data = conn.fetch(eid, "(RFC822)")
        if status != "OK":
            continue
        msg = email.message_from_bytes(msg_data[0][1])
        subject = _decode(msg.get("Subject"))
        body = _get_body(msg)
        full_text = f"{subject}\n{body}"

        result = matcher.process_alert_text(full_text, source="email")
        logging.info("Email processed: subject=%r result=%s", subject, result)

    conn.logout()


def main():
    logging.info("Starting email watcher, polling every %ss", POLL_SECONDS)
    while True:
        try:
            poll_once()
        except Exception:
            logging.exception("Error during email poll")
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
