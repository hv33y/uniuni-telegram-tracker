import os
import json
import requests
from datetime import datetime, timedelta

# --- Config ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
UNIUNI_API_KEY = os.getenv("UNIUNI_API_KEY")

if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
    raise Exception("Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID!")
if not UNIUNI_API_KEY:
    print("[WARN] UNIUNI_API_KEY not set. UniUni tracking will be skipped.")

STATUS_FILE = "status.json"
TRACKING_FILE = "tracking.txt"
RESET_TRACKING = os.getenv("INPUT_RESET_TRACKING", "no").lower() == "yes"

# Load previous status
if os.path.exists(STATUS_FILE) and not RESET_TRACKING:
    with open(STATUS_FILE, "r") as f:
        previous_status = json.load(f)
else:
    previous_status = {}

current_status = {}

# Load tracking numbers
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

# --- Helper functions ---
def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
    response = requests.post(url, data=data)
    if not response.ok:
        print(f"[ERROR] Failed to send Telegram message: {response.text}")

def est_from_unix(ts):
    dt = datetime.utcfromtimestamp(ts) - timedelta(hours=5)
    return dt.strftime("%Y-%m-%d %H:%M")

# --- UniUni Handler ---
def handle_uniuni(tracking):
    if not UNIUNI_API_KEY:
        return []

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

# --- FedEx Handler ---
def handle_fedex(tracking):
    api_url = f"https://www.fedex.com/trackingCal/track?data={{\"TrackPackagesRequest\":{\"appType\":\"wtrk\",\"trackingInfo\":[{{\"trackingNumberInfo\":{{\"trackingNumber\":\"{tracking}\"}}}}],\"trackingNumberInfo\":{\"trackingNumber\":\"{tracking}\"},\"action\":\"trackpackages\",\"language\":\"en\",\"locale\":\"en_US\",\"version\":\"1\"}}}}"
    resp = requests.get(api_url)
    if not resp.ok:
        print(f"[WARN] FedEx API failed for {tracking}")
        return []

    data = resp.json()
    events = []

    for pkg in data.get("TrackPackagesResponse", {}).get("packageList", []):
        for event in pkg.get("scanEventList", []):
            ts = event.get("date")  # ISO format
            time_str = ts.replace("T", " ").split("-")[0] if ts else "Unknown"
            events.append({
                "time": time_str,
                "status": event.get("status", ""),
                "location": event.get("scanLocation", "")
            })
    return events

# --- Main processing ---
uniuni_updates = []
fedex_updates = []

for tracking in TRACKING_NUMBERS:
    print(f"[INFO] Checking tracking number {tracking}")

    if tracking.startswith("N25"):
        events = handle_uniuni(tracking)
        if not events or previous_status.get(tracking) == events:
            continue
        uniuni_updates.append((tracking, events))
        current_status[tracking] = events

    elif tracking.startswith("FE"):
        events = handle_fedex(tracking)
        if not events or previous_status.get(tracking) == events:
            continue
        fedex_updates.append((tracking, events))
        current_status[tracking] = events

    else:
        print(f"[WARN] Unknown carrier for {tracking}")
        continue

# --- Send Telegram message ---
messages = []

if uniuni_updates:
    messages.append("**UniUni Tracker Updates:**")
    for tracking, events in uniuni_updates:
        messages.append(f"Tracking: {tracking}")
        for ev in events:
            messages.append(f"{ev['time']} | {ev['location']} | {ev['status']}")
        messages.append("")

if fedex_updates:
    messages.append("**FedEx Tracker Updates:**")
    for tracking, events in fedex_updates:
        messages.append(f"Tracking: {tracking}")
        for ev in events:
            messages.append(f"{ev['time']} | {ev['location']} | {ev['status']}")
        messages.append("")

if messages:
    send_telegram("\n".join(messages))
    print("[INFO] Sent updates to Telegram")
else:
    print("[INFO] No new updates to send")

with open(STATUS_FILE, "w") as f:
    json.dump(current_status, f, indent=2)
