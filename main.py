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

RESET_TRACKING = os.getenv("INPUT_RESET_TRACKING", "no").lower() == "yes"

if os.path.exists(STATUS_FILE) and not RESET_TRACKING:
    with open(STATUS_FILE, "r") as f:
        previous_status = json.load(f)
else:
    previous_status = {}

current_status = {}

# Read tracking numbers
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

# --- UniUni handler ---
def handle_uniuni(tracking):
    api_url = f"https://delivery-api.uniuni.ca/cargo/trackinguniuninew?id={tracking}&key={UNIUNI_API_KEY}"
    resp = requests.get(api_url)
    if not resp.ok:
        print(f"[WARN] UniUni API failed for {tracking}")
        return []

    data = resp.json()
    valid_list = data.get("data", {}).get("valid_tno", [])
    events = []

    if not valid_list:
        print(f"[WARN] No valid UniUni info for {tracking}")
        return []

    for spath in valid_list[0].get("spath_list", []):
        ts = spath.get("pathTime")
        if ts:
            events.append({
                "time": est_from_unix(int(ts)),
                "status": spath.get("pathInfo"),
                "location": spath.get("pathAddr", "")
            })
    return events

# --- FedEx handler ---
def handle_fedex(tracking):
    api_url = f"https://www.fedex.com/trackingCal/track?data={{\"TrackPackagesRequest\":{\"appType\":\"wtrk\",\"trackingInfo\":[{{\"trackingNumberInfo\":{{\"trackingNumber\":\"{tracking}\"}}}}],\"trackingNumberInfo\":{\"trackingNumber\":\"{tracking}\"},\"action\":\"trackpackages\",\"language\":\"en\",\"locale\":\"en_US\",\"version\":\"1\"}}}}"
    resp = requests.get(api_url)
    if not resp.ok:
        print(f"[WARN] FedEx API failed for {tracking}")
        return []

    data = resp.json()
    events = []

    # Simple parser: you can adjust based on FedEx API JSON structure
    for pkg in data.get("TrackPackagesResponse", {}).get("packageList", []):
        for event in pkg.get("scanEventList", []):
            ts = event.get("date")  # usually "2025-12-02T14:32:00-05:00"
            time_str = ts.replace("T", " ").split("-")[0] if ts else "Unknown"
            events.append({
                "time": time_str,
                "status": event.get("status", ""),
                "location": event.get("scanLocation", "")
            })
    return events

# --- Main loop ---
for tracking in TRACKING_NUMBERS:
    print(f"[INFO] Checking tracking number {tracking}")

    # Decide carrier
    if tracking.startswith("N25"):
        events = handle_uniuni(tracking)
    elif tracking.startswith("FE"):
        events = handle_fedex(tracking)
    else:
        print(f"[WARN] Unknown carrier for {tracking}")
        continue

    if not events:
        continue

    if previous_status.get(tracking) == events:
        continue

    current_status[tracking] = events

    msg_lines = [f"Tracking Update for {tracking}:"]
    for ev in events:
        line = f"{ev['time']} | {ev['location']} | {ev['status']}"
        msg_lines.append(line)

    send_telegram("\n".join(msg_lines))
    print(f"[INFO] Sent update for {tracking}")

with open(STATUS_FILE, "w") as f:
    json.dump(current_status, f, indent=2)
