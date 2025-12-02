import os
import json
import requests
from datetime import datetime, timedelta

# Telegram config
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
UNIUNI_API_KEY = os.getenv("UNIUNI_API_KEY")

if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID or not UNIUNI_API_KEY:
    raise Exception("Missing TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, or UNIUNI_API_KEY!")

STATUS_FILE = "status.json"
TRACKING_FILE = "tracking.txt"

# Workflow input to reset all statuses
RESET_TRACKING = os.getenv("INPUT_RESET_TRACKING", "no").lower() == "yes"

# Load previous status to avoid duplicate notifications
if os.path.exists(STATUS_FILE) and not RESET_TRACKING:
    with open(STATUS_FILE, "r") as f:
        previous_status = json.load(f)
else:
    previous_status = {}

current_status = {}

# Read tracking numbers from file
TRACKING_NUMBERS = []
if os.path.exists(TRACKING_FILE):
    with open(TRACKING_FILE, "r") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                TRACKING_NUMBERS.append(line)

if not TRACKING_NUMBERS:
    print("[WARN] No tracking numbers found in tracking.txt")
    exit(0)

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
    response = requests.post(url, data=data)
    if not response.ok:
        print(f"[ERROR] Failed to send Telegram message: {response.text}")

def est_from_unix(ts):
    dt = datetime.utcfromtimestamp(ts) - timedelta(hours=5)
    return dt.strftime("%Y-%m-%d %H:%M")

for tracking in TRACKING_NUMBERS:
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
