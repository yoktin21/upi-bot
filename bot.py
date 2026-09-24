"""
UPPCS Prelims bot — plain UPI link, no payment gateway.
/start    - welcome
/buy      - generates a ₹2000 UPI QR/link, queues you for auto-match
/status   - check your payment status
/pending  - (admin only) list unmatched pending requests
/approve <telegram_id> - (admin only) manually mark someone paid

Run: python bot.py
Also run email_watcher.py and/or webhook_server.py so payments can be
auto-detected; without either of those running, only /approve works.
"""
import os
import logging
from aiogram import Bot, Dispatcher
from aiogram.filters import Command, CommandObject
from aiogram.types import Message, BufferedInputFile
from dotenv import load_dotenv

import db
import upi_link

load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_IDS = {int(x) for x in os.getenv("ADMIN_TELEGRAM_IDS", "").split(",") if x.strip()}
PRICE_INR = 2000

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

db.init_db()


def is_admin(telegram_id: int) -> bool:
    return telegram_id in ADMIN_IDS


@dp.message(Command("start"))
async def start_handler(message: Message):
    db.upsert_user(message.from_user.id, message.from_user.username)
    await message.answer(
        "👋 Welcome to the <b>UPPCS Prelims</b> prep bot!\n\n"
        f"Access: a one-time payment of ₹{PRICE_INR} via UPI — no gateway, "
        "no recurring charge.\n\n"
        "Use /buy to get your payment QR, /status to check.",
        parse_mode="HTML",
    )


@dp.message(Command("buy"))
async def buy_handler(message: Message):
    user = db.get_user(message.from_user.id)
    if user and user["status"] == "paid":
        await message.answer("✅ You've already paid — you have full access.")
        return

    db.upsert_user(message.from_user.id, message.from_user.username)
    note_code = upi_link.make_note_code(message.from_user.id)
    db.create_pending(message.from_user.id, note_code)

    link = upi_link.build_upi_link(message.from_user.id, note_code)
    qr_bytes = upi_link.build_qr_png_bytes(link)

    await message.answer_photo(
        BufferedInputFile(qr_bytes, filename="pay.png"),
        caption=(
            f"Scan to pay ₹{PRICE_INR} via any UPI app, or tap the link below "
            "on mobile.\n\n"
            f"🔗 {link}\n\n"
            "Once your payment lands, I'll detect it automatically and confirm "
            "here — usually within a minute or two. If it takes longer, an "
            "admin can confirm it manually."
        ),
    )


@dp.message(Command("status"))
async def status_handler(message: Message):
    user = db.get_user(message.from_user.id)
    if not user or user["status"] in ("none", None):
        await message.answer("No payment on record yet. Use /buy.")
        return
    status_map = {
        "pending": "⏳ Waiting for payment / confirmation. Use /buy again to see your QR.",
        "paid": "✅ Paid — you have full access.",
    }
    await message.answer(status_map.get(user["status"], user["status"]))


@dp.message(Command("pending"))
async def pending_handler(message: Message):
    if not is_admin(message.from_user.id):
        return
    rows = db.get_pending_oldest_first()
    if not rows:
        await message.answer("No pending requests.")
        return
    lines = [
        f"• {r['telegram_id']} (@{r['username']}) — requested {r['requested_at']}"
        for r in rows
    ]
    await message.answer("Pending:\n" + "\n".join(lines))


@dp.message(Command("approve"))
async def approve_handler(message: Message, command: CommandObject):
    if not is_admin(message.from_user.id):
        return
    if not command.args:
        await message.answer("Usage: /approve <telegram_id>")
        return
    try:
        target_id = int(command.args.strip())
    except ValueError:
        await message.answer("telegram_id must be a number.")
        return

    db.mark_paid(target_id, matched_by="manual", match_detail=f"approved by {message.from_user.id}")
    await message.answer(f"Marked {target_id} as paid.")
    try:
        await bot.send_message(
            target_id,
            "✅ Your ₹2000 payment has been confirmed manually — you now have full access.",
        )
    except Exception:
        logging.exception("Could not DM approved user")


async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
