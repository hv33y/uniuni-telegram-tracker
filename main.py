import os
import json
import requests
from datetime import datetime, timedelta
from email.utils import formataddr

# Telegram config
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
UNIUNI_API_KEY = os.getenv("UNIUNI_API_KEY")

if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID or not UNIUNI_API_KEY:
    raise Exception("Missing TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, or UNIUNI_API_KEY!")

# Tracking numbers (comma-separated)
TRACKING_NUMBERS = os.getenv("INPUT_ADD_TRACKING", "").split(",")
STOP_TRACKING = os.getenv("INPUT_STOP_TRACKING", "").split(",")

STATUS_FILE = "status.json"

# Load previous status to avoid duplicate notifications
if os.path.exists(STATUS_FILE):
    with open(STATUS_FILE, "r") as f:
        previous_status = json.load(f)
else:
    previous_status = {}

current_status = {}

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
    response = requests.post(url, data=data)
    if not response.ok:
        print(f"[ERROR] Failed to send Telegram message: {response.text}")

def est_from_unix(ts):
    # Convert Unix timestamp to EST (UTC-5)
    dt = datetime.utcfromtimestamp(ts) - timedelta(hours=5)
    return dt.strftime("%Y-%m-%d %H:%M")

for tracking in TRACKING_NUMBERS:
    tracking = tracking.strip()
    if not tracking or tracking in STOP_TRACKING:
        continue

    print(f"[INFO] Checking tracking number {tracking}")
    api_url = f"https://delivery-api.uniuni.ca/cargo/trackinguniuninew?id={tracking}&key={UNIUNI_API_KEY}"
    resp = requests.get(api_url)
    if not resp.ok:
        print(f"[WARN] Failed to fetch tracking info for {tracking}")
        continue

    data = resp.json()
    valid_list = data.get("data", {}).get("valid_tno", [])

    if not valid_list:
        print(f"[WARN] No valid tracking info for {tracking}")
        continue

    events = []
    for spath in valid_list[0].get("spath_list", []):
        ts = spath.get("pathTime")
        if ts:
            events.append({
                "time": est_from_unix(int(ts)),
                "status": spath.get("pathInfo"),
                "location": spath.get("pathAddr", "")
            })

    # Skip if nothing changed
    if previous_status.get(tracking) == events:
        continue

    # Save current status
    current_status[tracking] = events

    # Build message
    msg_lines = [f"Tracking Update for {tracking}:"]
    for ev in events:
        line = f"{ev['time']} | {ev['location']} | {ev['status']}"
        msg_lines.append(line)

    send_telegram("\n".join(msg_lines))
    print(f"[INFO] Sent update for {tracking}")

# Save status.json
with open(STATUS_FILE, "w") as f:
    json.dump(current_status, f, indent=2)
