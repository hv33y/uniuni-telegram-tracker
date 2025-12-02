import json
import os
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import pytz

STATUS_FILE = "status.json"

# Env variables
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

# Manage tracking numbers
tracking_numbers = list(status_data.keys())

if INPUT_ADD_TRACKING:
    if INPUT_ADD_TRACKING not in tracking_numbers:
        tracking_numbers.append(INPUT_ADD_TRACKING)
        print(f"[INFO] Added tracking number: {INPUT_ADD_TRACKING}")
    else:
        print(f"[INFO] Tracking number {INPUT_ADD_TRACKING} already exists.")

if INPUT_STOP_TRACKING:
    if INPUT_STOP_TRACKING in tracking_numbers:
        tracking_numbers.remove(INPUT_STOP_TRACKING)
        status_data.pop(INPUT_STOP_TRACKING, None)
        print(f"[INFO] Stopped tracking number: {INPUT_STOP_TRACKING}")
    else:
        print(f"[INFO] Tracking number {INPUT_STOP_TRACKING} not found.")

# Function to fetch UniUni status
def fetch_uniuni_status(tracking_number):
    url = f"https://www.uniuni.com/tracking/?tracking_number={tracking_number}"
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        print(f"[ERROR] Failed to fetch tracking page: {e}")
        return None

    soup = BeautifulSoup(resp.text, "html.parser")
    
    # Find the first row of tracking table (latest event)
    table = soup.find("table")
    if not table:
        print("[WARN] No tracking table found")
        return None
    
    rows = table.find_all("tr")
    if len(rows) < 2:
        print("[WARN] No tracking data rows found")
        return None

    latest_row = rows[1]  # skip header
    cols = latest_row.find_all("td")
    if len(cols) < 2:
        print("[WARN] Not enough columns in tracking row")
        return None

    status_text = cols[0].get_text(strip=True)
    time_text = cols[1].get_text(strip=True)
    location_text = cols[2].get_text(strip=True) if len(cols) > 2 else "N/A"

    # Convert to EST timezone
    try:
        # Assuming time_text is in UTC or UniUni local time (adjust if needed)
        dt = datetime.strptime(time_text, "%Y-%m-%d %H:%M")
        dt_utc = dt.replace(tzinfo=pytz.UTC)
        est_tz = pytz.timezone("US/Eastern")
        dt_est = dt_utc.astimezone(est_tz)
        formatted_time = dt_est.strftime("%b %d %Y %I:%M %p EST")
    except:
        formatted_time = time_text  # fallback

    return {
        "status": status_text,
        "location": location_text,
        "timestamp": formatted_time
    }

# Telegram sending
def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
    try:
        r = requests.post(url, json=payload)
        print(f"[INFO] Telegram response: {r.status_code}")
    except Exception as e:
        print(f"[ERROR] Failed to send Telegram message: {e}")

# Main tracking loop
for tracking_number in tracking_numbers:
    print(f"[INFO] Checking tracking number {tracking_number}")

    new_status = fetch_uniuni_status(tracking_number)
    if not new_status:
        continue

    old_status = status_data.get(tracking_number)

    # Compare latest event timestamp to decide if update is new
    if not old_status or old_status.get("timestamp") != new_status["timestamp"]:
        status_data[tracking_number] = new_status
        message = (
            f"Tracking Update for {tracking_number}:\n"
            f"Status: {new_status['status']}\n"
            f"Location: {new_status['location']}\n"
            f"Time: {new_status['timestamp']}"
        )
        send_telegram(message)
        print(f"[INFO] Sent Telegram update for {tracking_number}")
    else:
        print(f"[INFO] No new update for {tracking_number}, skipping notification.")

# Save updated status
with open(STATUS_FILE, "w") as f:
    json.dump(status_data, f, indent=2)
