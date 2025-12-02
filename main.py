import json
import os
import requests
from datetime import datetime

STATUS_FILE = "status.json"
TRACKING_NUMBERS_FILE = "tracking_numbers.json"  # optional if you want persistent list

# Environment variables
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
INPUT_ADD_TRACKING = os.environ.get("INPUT_ADD_TRACKING", "").strip()
INPUT_STOP_TRACKING = os.environ.get("INPUT_STOP_TRACKING", "").strip()

if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
    raise Exception("Telegram bot token or chat ID missing!")

# Load or initialize status mapping
if os.path.exists(STATUS_FILE):
    with open(STATUS_FILE, "r") as f:
        status_data = json.load(f)
else:
    status_data = {}

# Manage tracking numbers dynamically
tracking_numbers = list(status_data.keys())

if INPUT_ADD_TRACKING:
    if INPUT_ADD_TRACKING not in tracking_numbers:
        tracking_numbers.append(INPUT_ADD_TRACKING)
        print(f"Added tracking number: {INPUT_ADD_TRACKING}")
    else:
        print(f"Tracking number {INPUT_ADD_TRACKING} already exists.")

if INPUT_STOP_TRACKING:
    if INPUT_STOP_TRACKING in tracking_numbers:
        tracking_numbers.remove(INPUT_STOP_TRACKING)
        print(f"Stopped tracking number: {INPUT_STOP_TRACKING}")
        status_data.pop(INPUT_STOP_TRACKING, None)
    else:
        print(f"Tracking number {INPUT_STOP_TRACKING} not found.")

# Dummy UniUni API fetch function
def fetch_uniuni_status(tracking_number):
    """
    Replace this function with actual API or scraping logic.
    Returns a string representing the current status.
    """
    # Example simulation: Just returns "In Transit" for demo
    return "In Transit"

# Telegram sending function with logging
def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
    try:
        r = requests.post(url, json=payload)
        print(f"[{datetime.now()}] Telegram response: {r.status_code}, {r.text}")
    except Exception as e:
        print(f"[{datetime.now()}] Failed to send Telegram message: {e}")

# Main tracking loop
for tracking_number in tracking_numbers:
    print(f"[{datetime.now()}] Checking tracking number {tracking_number}")

    old_status = status_data.get(tracking_number)
    new_status = fetch_uniuni_status(tracking_number)
    print(f"[{datetime.now()}] Old status: {old_status}")
    print(f"[{datetime.now()}] New status: {new_status}")

    if old_status != new_status:
        status_data[tracking_number] = new_status
        message = f"Tracking Update for {tracking_number}:\n{new_status}"
        send_telegram(message)
    else:
        print(f"[{datetime.now()}] No change for {tracking_number}, skipping notification.")

# Save updated status
with open(STATUS_FILE, "w") as f:
    json.dump(status_data, f, indent=2)
