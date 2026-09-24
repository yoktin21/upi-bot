"""
Builds a plain UPI deep link (no gateway) and a QR code image for it.

Note: the 'tn' (transaction note) field is included for reference, but
most banks do NOT echo it back in SMS/email credit alerts — treat it as
best-effort, not guaranteed. Matching in this bot primarily relies on
amount + FIFO order within a time window (see matcher.py), with manual
/approve as the safety net.
"""
import io
import os
import urllib.parse
import qrcode
from dotenv import load_dotenv

load_dotenv()

UPI_VPA = os.getenv("UPI_VPA")          # e.g. yourname@okhdfcbank
PAYEE_NAME = os.getenv("PAYEE_NAME", "UPPCS Prelims")
AMOUNT_INR = 2000


def build_upi_link(telegram_id: int, note_code: str) -> str:
    params = {
        "pa": UPI_VPA,
        "pn": PAYEE_NAME,
        "am": f"{AMOUNT_INR}.00",
        "cu": "INR",
        "tn": note_code,
    }
    return "upi://pay?" + urllib.parse.urlencode(params)


def build_qr_png_bytes(upi_link: str) -> bytes:
    img = qrcode.make(upi_link)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf.read()


def make_note_code(telegram_id: int) -> str:
    # Short, human-typeable code the user could quote in support chats;
    # not guaranteed to survive into the bank's SMS/email.
    return f"UPPCS{telegram_id % 100000}"
