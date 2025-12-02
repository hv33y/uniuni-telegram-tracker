import os
import json
import requests
from datetime import datetime, timedelta

# ENV VARIABLES
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
UNIUNI_API_KEY = os.getenv("UNIUNI_API_KEY")

TRACKING_FILE = "tracking.json"

if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
    raise Exception("Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID!")

# Load or initialize tracking file
if os.path.exists(TRACKING_FILE):
    with open(TRACKING_FILE, "r") as f:
        tracking_data = json.load(f)
else:
    tracking_data = {"uniuni": {}, "fedex": {}}

# Only require UNIUNI_API_KEY if there are UniUni tracking numbers
if tracking_data.get("uniuni") and not UNIUNI_API_KEY:
    raise Exception("Missing UNIUNI_API_KEY for UniUni tracking!")

def save_tracking_file():
    with open(TRACKING_FILE, "w") as f:
        json.dump(tracking_data, f, indent=2)

# ------------------- Telegram -------------------
def send_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    resp = requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": text})
    if not resp.ok:
        print(f"[WARN] Failed to send Telegram message: {resp.text}")

# ------------------- UniUni -------------------
def handle_uniuni(tracking):
    url = f"https://delivery-api.uniuni.ca/cargo/trackinguniuninew?id={tracking}&key={UNIUNI_API_KEY}"
    resp = requests.get(url)
    if not resp.ok:
        print(f"[WARN] UniUni API failed for {tracking}")
        return []

    data = resp.json()
    events = []
    for pkg in data.get("data", {}).get("valid_tno", []):
        for spath in pkg.get("spath_list", []):
            ts_epoch = spath.get("pathTime")
            if ts_epoch:
                dt = datetime.utcfromtimestamp(ts_epoch) - timedelta(hours=5)  # EST
                time_str = dt.strftime("%Y-%m-%d %H:%M")
            else:
                time_str = "Unknown"
            events.append({
                "time": time_str,
                "status": spath.get("pathInfo", ""),
                "location": spath.get("pathAddr", "")
            })
    return events

# ------------------- FedEx -------------------
def handle_fedex(tracking):
    url = "https://www.fedex.com/trackingCal/track"
    payload = {
        "TrackPackagesRequest": {
            "appType": "wtrk",
            "trackingInfo": [{"trackingNumberInfo": {"trackingNumber": tracking}}],
            "action": "trackpackages",
            "language": "en",
            "locale": "en_US",
            "version": "1"
        }
    }
    resp = requests.get(url, params={"data": json.dumps(payload)})
    if not resp.ok:
        print(f"[WARN] FedEx API failed for {tracking}")
        return []

    data = resp.json()
    events = []

    for pkg in data.get("TrackPackagesResponse", {}).get("packageList", []):
        for event in pkg.get("scanEventList", []):
            ts = event.get("date")  # ISO format
            if ts:
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00")) - timedelta(hours=5)  # EST
                time_str = dt.strftime("%Y-%m-%d %H:%M")
            else:
                time_str = "Unknown"
            events.append({
                "time": time_str,
                "status": event.get("status", ""),
                "location": event.get("scanLocation", "")
            })
    return events

# ------------------- Process tracking -------------------
def process_tracking(tracker_type):
    new_events = []
    for tracking, last_status in tracking_data.get(tracker_type, {}).items():
        if tracker_type == "uniuni":
            events = handle_uniuni(tracking)
        elif tracker_type == "fedex":
            events = handle_fedex(tracking)
        else:
            continue

        if not events:
            print(f"[WARN] No events for {tracking}")
            continue

        latest = events[-1]
        last = last_status.get("last_event")
        if last != latest:
            tracking_data[tracker_type][tracking]["last_event"] = latest
            new_events.append((tracking, latest))

    return new_events

# ------------------- Send notifications -------------------
def notify(events, tracker_type):
    for tracking, event in events:
        msg = f"{tracker_type.upper()} Tracking Update for {tracking}:\n{event['time']} - {event['status']}"
        if event["location"]:
            msg += f" ({event['location']})"
        send_telegram(msg)

# ------------------- MAIN -------------------
if __name__ == "__main__":
    for tracker_type in ["uniuni", "fedex"]:
        for tracking in tracking_data.get(tracker_type, {}):
            tracking_data[tracker_type][tracking].setdefault("last_event", None)

    uniuni_events = process_tracking("uniuni") if tracking_data.get("uniuni") else []
    fedex_events = process_tracking("fedex") if tracking_data.get("fedex") else []

    notify(uniuni_events, "uniuni")
    notify(fedex_events, "fedex")

    save_tracking_file()
