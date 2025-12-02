import os
import json
import requests

# Import tracker modules
from trackers import uniuni

TRACKING_NUMBERS = os.getenv("TRACKING_NUMBERS", "").split(",")
STATUS_FILE = "status.json"
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Map tracking numbers to tracker module
TRACKER_MAPPING = {num.strip(): uniuni for num in TRACKING_NUMBERS}

def load_statuses():
    try:
        with open(STATUS_FILE, "r") as f:
            return json.load(f)
    except:
        return {}

def save_statuses(data):
    with open(STATUS_FILE, "w") as f:
        json.dump(data, f)

def send_telegram(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print("Telegram send error:", e)

def main():
    statuses = load_statuses()
    updates = []

    for tracking, tracker_module in TRACKER_MAPPING.items():
        try:
            status, checkpoint = tracker_module.get_status(tracking)
            old_status = statuses.get(tracking)
            if status != old_status:
                updates.append(f"{tracking}: {status}\n{checkpoint}")
                statuses[tracking] = status
        except Exception as e:
            updates.append(f"{tracking}: ERROR {e}")

    if updates:
        send_telegram("\n\n".join(updates))

    save_statuses(statuses)

if __name__ == "__main__":
    main()
