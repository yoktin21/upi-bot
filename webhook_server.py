"""
Receives bank SMS forwarded from your phone and feeds them into
matcher.process_alert_text().

Your phone doesn't run this — it runs a small Android "SMS forwarder"
app (e.g. MacroDroid, Automate, Tasker, or a dedicated "SMS to URL/
Webhook" app from Play Store) configured to POST incoming SMS to:

    https://yourdomain.com/sms/incoming
    Body (JSON): {"sender": "<SMS sender id>", "text": "<full SMS text>", "secret": "<SMS_WEBHOOK_SECRET>"}

Adjust the field names below to whatever your chosen forwarder app sends
— most let you customize the JSON body/template.

Run: python webhook_server.py
"""
import os
import logging
from flask import Flask, request, abort
from dotenv import load_dotenv

import matcher

load_dotenv()

SMS_WEBHOOK_SECRET = os.getenv("SMS_WEBHOOK_SECRET", "")

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)


@app.route("/sms/incoming", methods=["POST"])
def sms_incoming():
    data = request.get_json(silent=True) or {}

    if SMS_WEBHOOK_SECRET and data.get("secret") != SMS_WEBHOOK_SECRET:
        abort(403)

    text = data.get("text", "")
    sender = data.get("sender", "")
    if not text:
        return {"status": "ignored", "reason": "no text field"}, 200

    result = matcher.process_alert_text(text, source="sms")
    logging.info("SMS from %s processed: %s", sender, result)
    return {"status": "ok", "result": result}, 200


@app.route("/health", methods=["GET"])
def health():
    return {"status": "up"}, 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
