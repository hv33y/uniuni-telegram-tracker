import os
import json
import requests
import logging
import argparse
import base64
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Configuration
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
ADMIN_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID") 
FEDEX_CLIENT_ID = os.environ.get("FEDEX_CLIENT_ID")
FEDEX_CLIENT_SECRET = os.environ.get("FEDEX_CLIENT_SECRET")
UPS_CLIENT_ID = os.environ.get("UPS_CLIENT_ID")
UPS_CLIENT_SECRET = os.environ.get("UPS_CLIENT_SECRET")
DATA_FILE = "tracking.json"

def load_data():
    default_structure = {"users": {}}
    if not os.path.exists(DATA_FILE): return default_structure
    try:
        with open(DATA_FILE, 'r') as f: data = json.load(f)
        if "packages" in data and isinstance(data["packages"], list):
            old_packages = data.pop("packages")
            if ADMIN_CHAT_ID: data.setdefault("users", {})[str(ADMIN_CHAT_ID)] = old_packages
            save_data(data)
        if "users" not in data: data["users"] = {}
        return data
    except json.JSONDecodeError: return default_structure

def save_data(data):
    try:
        with open(DATA_FILE, 'w') as f: json.dump(data, f, indent=2)
    except Exception as e: logging.error(f"Failed to save data: {e}")

def set_github_output(name, value):
    output_path = os.environ.get("GITHUB_OUTPUT")
    if output_path:
        with open(output_path, "a") as f: f.write(f"{name}={value}\n")
    else: print(f"::set-output name={name}::{value}")

def send_telegram_message(chat_id, message, buttons=None, message_id=None):
    """
    Sends or Edits a Telegram message.
    If message_id is provided, it tries to EDIT that message.
    If edit fails (or no ID), it SENDS a new one.
    """
    if not TELEGRAM_BOT_TOKEN or not chat_id: return

    # Try EDIT first if we have an ID
    if message_id:
        edit_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/editMessageText"
        edit_payload = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": message,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True
        }
        if buttons: edit_payload["reply_markup"] = {"inline_keyboard": buttons}
        
        try:
            r = requests.post(edit_url, json=edit_payload)
            if r.status_code == 200: return # Edit successful, stop here
            logging.warning(f"Edit failed (HTTP {r.status_code}): {r.text}")
        except Exception as e:
            logging.error(f"Edit Exception: {e}")

    # Fallback: SEND new message
    send_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    send_payload = {
        "chat_id": chat_id, 
        "text": message, 
        "parse_mode": "Markdown", 
        "disable_web_page_preview": True
    }
    if buttons: send_payload["reply_markup"] = {"inline_keyboard": buttons}
    
    try: 
        requests.post(send_url, json=send_payload).raise_for_status()
    except Exception as e: 
        logging.error(f"Send Error for {chat_id}: {e}")

def format_time(timestamp, is_unix=False, custom_format=None):
    if not timestamp: return ""
    try:
        if is_unix: dt = datetime.fromtimestamp(timestamp)
        elif custom_format: dt = datetime.strptime(timestamp, custom_format)
        else:
            clean_ts = timestamp.replace("Z", "").split(".")[0]
            dt = datetime.fromisoformat(clean_ts)
        return dt.strftime("%Y-%m-%d %I:%M %p") 
    except: return str(timestamp)

# --- TRACKING FUNCTIONS (Unchanged logic, compacted for brevity) ---
def track_uniuni(tracking_number, full_history=False):
    API_KEY = "SMq45nJhQuNR3WHsJA6N" 
    url = "https://delivery-api.uniuni.ca/cargo/trackinguniuninew"
    try:
        r = requests.get(url, params={"id": tracking_number, "key": API_KEY}, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
        if r.status_code != 200: return {"status": f"HTTP {r.status_code}", "details": "Error", "events": [], "url": ""}
        d = r.json().get("data", {}).get("valid_tno", [])
        if not d: return {"status": "No Data", "details": "Not found", "events": [], "url": ""}
        evs = d[0].get("spath_list", [])
        if not evs: return {"status": "Label Created", "details": "No scans", "events": [], "url": ""}
        lat = evs[0]
        desc = lat.get("pathInfo") or lat.get("code") or "Update"
        loc = lat.get("pathAddr") or lat.get("pathAddress") or ""
        tm = format_time(lat.get("pathTime"), True)
        det = f"{desc} ({loc}) @ {tm}" if tm else desc
        hist = []
        if full_history:
            for e in evs:
                t = format_time(e.get("pathTime"), True)
                l = f"🕒 *{t}*\n└ {e.get('pathInfo') or e.get('code')}"
                if e.get('pathAddr'): l += f" ({e.get('pathAddr')})"
                hist.append(l)
        return {"status": "Active", "details": det, "events": hist, "url": f"https://www.uniuni.com/tracking/?tracking_number={tracking_number}"}
    except Exception as e: return {"status": "Error", "details": str(e), "events": [], "url": ""}

def track_fedex(tracking_number, full_history=False):
    if not FEDEX_CLIENT_ID or not FEDEX_CLIENT_SECRET: return {"status": "Auth Error", "details": "Check Keys", "events": [], "url": ""}
    # Auth Logic omitted for brevity, assumes working token fetch
    try:
        # (Using previous working logic)
        token_url = "https://apis.fedex.com/oauth/token"
        r = requests.post(token_url, data={"grant_type": "client_credentials", "client_id": FEDEX_CLIENT_ID, "client_secret": FEDEX_CLIENT_SECRET}, timeout=10)
        token = r.json().get("access_token")
        if not token: return {"status": "Auth Error", "details": "Check Keys", "events": [], "url": ""}
        
        url = "https://apis.fedex.com/track/v1/trackingnumbers"
        r = requests.post(url, json={"trackingInfo": [{"trackingNumberInfo": {"trackingNumber": tracking_number}}], "includeDetailedScans": True}, headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}, timeout=15)
        res = r.json().get("output", {}).get("completeTrackResults", [])[0].get("trackResults", [])[0]
        lat = res.get("latestStatusDetail", {})
        scans = res.get("scanEvents", [])
        tm = format_time(scans[0].get("date", "")) if scans else ""
        desc = lat.get("description", "In Transit")
        loc = f"{lat.get('scanLocation', {}).get('city', '')}".strip()
        det = f"{desc} ({loc}) @ {tm}" if loc else f"{desc} @ {tm}"
        hist = []
        if full_history:
            for s in scans:
                t = format_time(s.get("date", ""))
                l = f"🕒 *{t}*\n└ {s.get('eventDescription')}"
                if s.get('scanLocation', {}).get('city'): l += f" ({s.get('scanLocation', {}).get('city')})"
                hist.append(l)
        return {"status": "Active", "details": det, "events": hist, "url": f"https://www.fedex.com/fedextrack/?trknbr={tracking_number}"}
    except Exception as e: return {"status": "Error", "details": str(e), "events": [], "url": ""}

def track_ups(tracking_number, full_history=False):
    # Link Mode
    return {"status": "Link", "details": "Protected. Click to view.", "events": [], "url": f"https://www.ups.com/track?loc=en_US&tracknum={tracking_number}"}

def get_tracker(number):
    u = number.upper()
    if u.startswith("1Z"): return track_ups, "UPS"
    if u.isdigit() and len(u) in [12, 15, 20, 22]: return track_fedex, "FedEx"
    return track_uniuni, "UniUni"

# --- ACTIONS ---

def perform_check(force_report=False, specific_user_id=None, msg_id=None):
    data = load_data()
    users = data.get("users", {})
    target_users = [specific_user_id] if specific_user_id else list(users.keys())
    updates_found = False
    
    for user_id in target_users:
        user_id = str(user_id)
        packages = users.get(user_id, [])
        if not packages and specific_user_id:
            # Edit the "Loading" message to say empty
            send_telegram_message(user_id, "📭 **Tracking List is Empty**", [[{"text": "🔙 Back to Main Menu", "callback_data": "main_menu"}]], message_id=msg_id)
            continue

        report_lines = []
        history_buttons = []
        for pkg in packages:
            num = pkg['number']
            tracker_func, carrier = get_tracker(num)
            res = tracker_func(num)
            
            curr = res['details']
            if curr != pkg.get('last_details', '') and carrier != "UPS":
                updates_found = True
                pkg['last_status'] = res['status']
                pkg['last_details'] = curr

            if updates_found or force_report:
                icon = "🟢" if curr != pkg.get('last_details', '') else "📦"
                link = res.get('url', '')
                disp = f"[{num}]({link})" if link else f"`{num}`"
                report_lines.append(f"{icon} *{carrier}*: {disp}\n{curr}")
                if carrier != "UPS":
                    history_buttons.append([{"text": f"📜 History: {num}", "callback_data": f"history_{num}"}])

        if report_lines:
            header = "*🔔 Updates*" if not force_report else "*📋 Full Report*"
            msg = f"{header}\n\n" + "\n\n".join(report_lines)
            btns = history_buttons + [[{"text": "🔄 Refresh", "callback_data": "refresh"}], [{"text": "🔙 Back to Main Menu", "callback_data": "main_menu"}]]
            # Pass msg_id to overwrite the "Loading..." message
            send_telegram_message(user_id, msg, btns, message_id=msg_id)

    if updates_found: save_data(data)
    return updates_found

def send_history(number, user_id, msg_id=None):
    tracker_func, carrier = get_tracker(number)
    res = tracker_func(number, full_history=True)
    events = res.get("events", [])
    
    if not events: msg = f"📜 *History: {carrier}* `{number}`\n\n_No history available._"
    else:
        if len(events) > 15: events = events[:15] + ["... (older truncated)"]
        msg = f"📜 *History: {carrier}* `{number}`\n\n" + "\n\n".join(events)
    
    # BACK BUTTON: "view_all" goes back to the list in Worker
    btns = [[{"text": "🔙 Back to List", "callback_data": "view_all"}], [{"text": "🏠 Main Menu", "callback_data": "main_menu"}]]
    send_telegram_message(user_id, msg, btns, message_id=msg_id)
    return False

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", required=True)
    parser.add_argument("--number")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--user_id")
    parser.add_argument("--message_id") # NEW ARGUMENT
    args = parser.parse_args()
    
    changed = False
    # Pass message_id to functions
    if args.mode == "check": 
        changed = perform_check(force_report=args.force, specific_user_id=args.user_id, msg_id=args.message_id)
    elif args.mode == "history": 
        send_history(args.number, args.user_id, msg_id=args.message_id)
    
    elif args.mode == "add":
        data = load_data()
        uid = str(args.user_id)
        if uid not in data["users"]: data["users"][uid] = []
        n = args.number.strip()
        _, carrier = get_tracker(n)
        
        if not any(p['number'] == n for p in data["users"][uid]):
            data["users"][uid].append({"number": n, "last_status": "New"})
            save_data(data)
            # Edit the "Adding..." message
            send_telegram_message(uid, f"✅ **Added:** {carrier} `{n}`", [[{"text": "🔙 Main Menu", "callback_data": "main_menu"}]], message_id=args.message_id)
            changed = True
        else:
            send_telegram_message(uid, f"⚠️ Exists.", [[{"text": "🔙 Main Menu", "callback_data": "main_menu"}]], message_id=args.message_id)
            
    elif args.mode == "delete":
        data = load_data()
        uid = str(args.user_id)
        if uid in data["users"]:
            orig = len(data["users"][uid])
            data["users"][uid] = [p for p in data["users"][uid] if p['number'] != args.number]
            if len(data["users"][uid]) < orig:
                save_data(data)
                _, carrier = get_tracker(args.number)
                # Edit the "Deleting..." message
                send_telegram_message(uid, f"🗑️ **Deleted:** {carrier} `{args.number}`", [[{"text": "🔙 Back to List", "callback_data": "view_all"}]], message_id=args.message_id)
                changed = True
            else:
                send_telegram_message(uid, f"⚠️ Not found.", [[{"text": "🔙 Main Menu", "callback_data": "main_menu"}]], message_id=args.message_id)

    set_github_output("UPDATED", str(changed).lower())
