import os
import json
import requests
from datetime import datetime, timezone, timedelta

STATUS_FILE = "status.json"

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
UNIUNI_API_KEY = os.getenv("UNIUNI_API_KEY")
INPUT_ADD_TRACKING = os.getenv("INPUT_ADD_TRACKING", "").strip()
INPUT_STOP_TRACKING = os.getenv("INPUT_STOP_TRACKING", "").strip()

if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID or not UNIUNI_API_KEY:
    raise Exception("Missing TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, or UNIUNI_API_KEY!")

def load_statuses():
    try:
        with open(STATUS_FILE, "r") as f:
            return json.load(f)
    except:
        return {}

def save_statuses(data):
    with open(STATUS_FILE, "w") as f:
        json.dump(data, f, indent=2)

def fetch_uniuni_api(tracking_number):
    url = f"https://delivery-api.uniuni.ca/cargo/trackinguniuninew?id={tracking_number}&key={UNIUNI_API_KEY}"
    r = requests.get(url, timeout=15)
    r.raise_for_status()
    return r.json()

def get_latest_event(data):
    valid_tno = data.get("data", {}).get("valid_tno", [])
    if not valid_tno:
        return None
    t_entry = valid_tno[0]
    spath_list = t_entry.get("spath_list", [])
    if not spath_list:
        return None
    return spath_list[-1]  # last event = latest

def format_time(ts_seconds):
    try:
        dt = datetime.fromtimestamp(ts_seconds, tz=timezone.utc)
        est = dt - timedelta(hours=5)  # EST (UTC-5)
        return est.strftime("%Y-%m-%d %H:%M:%S EST")
    except Exception:
        return str(ts_seconds)

def send_telegram(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": msg}
    try:
        r = requests.post(url, json=payload, timeout=10)
        print("Telegram:", r.status_code, r.text)
    except Exception as e:
        print("Telegram send error:", e)

def main():
    statuses = load_statuses()
    updated = False

    # Build tracking list
    tracking_numbers = list(statuses.keys())
    if INPUT_ADD_TRACKING:
        if INPUT_ADD_TRACKING not in tracking_numbers:
            tracking_numbers.append(INPUT_ADD_TRACKING)
            print(f"[INFO] Added tracking number: {INPUT_ADD_TRACKING}")
    if INPUT_STOP_TRACKING and INPUT_STOP_TRACKING in tracking_numbers:
        tracking_numbers.remove(INPUT_STOP_TRACKING)
        statuses.pop(INPUT_STOP_TRACKING, None)
        print(f"[INFO] Removed tracking number: {INPUT_STOP_TRACKING}")

    for tno in tracking_numbers:
        try:
            resp = fetch_uniuni_api(tno)
        except Exception as e:
            print(f"[ERROR] Fetch API failed for {tno}: {e}")
            continue

        if resp.get("status") != "SUCCESS":
            print(f"[WARN] API returned non-success for {tno}: {resp}")
            continue

        event = get_latest_event(resp)
        if not event:
            print(f"[WARN] No tracking events found for {tno}")
            continue

        last_ts = statuses.get(tno, {}).get("pathTime")
        path_time = event.get("pathTime")
        if last_ts != path_time:
            desc = event.get("description_en", "")
            location = event.get("pathAddr", "")
            ts_str = format_time(path_time)
            msg = (
                f"Tracking Update — {tno}\n"
                f"Status: {desc}\n"
                f"Location: {location}\n"
                f"Time: {ts_str}"
            )
            send_telegram(msg)
            statuses[tno] = {
                "pathTime": path_time,
                "description": desc,
                "location": location
            }
            updated = True
        else:
            print(f"[INFO] No new update for {tno}")

    if updated or INPUT_ADD_TRACKING or INPUT_STOP_TRACKING:
        save_statuses(statuses)

if __name__ == "__main__":
    main()
