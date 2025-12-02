import os
import json
import requests
from trackers import uniuni

STATUS_FILE = "status.json"
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# GitHub workflow dispatch inputs
ADD_TRACKING = os.getenv("INPUT_ADD_TRACKING", "").strip()
STOP_TRACKING = os.getenv("INPUT_STOP_TRACKING", "").strip()

# Load existing tracking mapping
try:
    with open(STATUS_FILE, "r") as f:
        TRACKER_MAPPING = json.load(f)
except:
    TRACKER_MAPPING = {}  # {tracking_number: {"module": "uniuni", "last_status": "..." }}

# Handle adding new tracking
if ADD_TRACKING:
    if ADD_TRACKING not in TRACKER_MAPPING:
        TRACKER_MAPPING[ADD_TRACKING] = {"module": "uniuni", "last_status": None}
        print(f"Added tracking number: {ADD_TRACKING}")
    else:
        print(f"Tracking number {ADD_TRACKING} already exists")

# Handle stopping tracking
if STOP_TRACKING:
    if STOP_TRACKING in TRACKER_MAPPING:
        TRACKER_MAPPING.pop(STOP_TRACKING)
        print(f"Stopped tracking number: {STOP_TRACKING}")
    else:
        print(f"Tracking number {STOP_TRACKING} not found")

def send_telegram(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message, "parse_mode": "HTML"}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print("Telegram send error:", e)

def main():
    updates = []

    for tracking, info in TRACKER_MAPPING.items():
        tracker_module_name = info["module"]
        tracker_module = uniuni  # currently only uniuni
        try:
            status, checkpoint = tracker_module.get_status(tracking)
            old_status = info.get("last_status")
            if status != old_status:
                updates.append(f"{tracking}: {status}\n{checkpoint}")
                TRACKER_MAPPING[tracking]["last_status"] = status
        except Exception as e:
            updates.append(f"{tracking}: ERROR {e}")

    if updates:
        send_telegram("\n\n".join(updates))

    # Save updated statuses
    with open(STATUS_FILE, "w") as f:
        json.dump(TRACKER_MAPPING, f)

if __name__ == "__main__":
    main()
