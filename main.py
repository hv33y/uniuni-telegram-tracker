import os
import json
import requests
import logging
import argparse
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Configuration
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
# TELEGRAM_CHAT_ID is now only used for the Admin/Fallback or Migration
ADMIN_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID") 
FEDEX_CLIENT_ID = os.environ.get("FEDEX_CLIENT_ID")
FEDEX_CLIENT_SECRET = os.environ.get("FEDEX_CLIENT_SECRET")
DATA_FILE = "tracking.json"

def load_data():
    """Loads data and handles migration from single-user to multi-user format."""
    default_structure = {"users": {}}
    
    if not os.path.exists(DATA_FILE):
        return default_structure
        
    try:
        with open(DATA_FILE, 'r') as f:
            data = json.load(f)
            
        # --- MIGRATION LOGIC ---
        # If we see the old "packages" list at root, move it to the Admin's ID
        if "packages" in data and isinstance(data["packages"], list):
            logging.info("Migrating old data format to multi-user format...")
            old_packages = data.pop("packages")
            if ADMIN_CHAT_ID:
                data.setdefault("users", {})[str(ADMIN_CHAT_ID)] = old_packages
            else:
                logging.warning("No Admin ID found to migrate data to. Old data might be lost.")
                data["users"] = {}
            # Save immediately to finalize migration
            save_data(data)
            
        # Ensure "users" key exists
        if "users" not in data:
            data["users"] = {}
            
        return data
    except json.JSONDecodeError:
        return default_structure

def save_data(data):
    try:
        with open(DATA_FILE, 'w') as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logging.error(f"Failed to save data: {e}")

def set_github_output(name, value):
    output_path = os.environ.get("GITHUB_OUTPUT")
    if output_path:
        with open(output_path, "a") as f:
            f.write(f"{name}={value}\n")
    else:
        print(f"::set-output name={name}::{value}")

def send_telegram_message(chat_id, message, buttons=None):
    """Sends a message to a specific user (chat_id)."""
    if not TELEGRAM_BOT_TOKEN or not chat_id:
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "Markdown"
    }
    if buttons:
        payload["reply_markup"] = {"inline_keyboard": buttons}

    try:
        requests.post(url, json=payload).raise_for_status()
    except Exception as e:
        logging.error(f"Telegram Error for {chat_id}: {e}")

# --- Helper: Time Formatter ---
def format_time(timestamp, is_unix=False):
    if not timestamp: return ""
    try:
        if is_unix:
            dt = datetime.fromtimestamp(timestamp)
        else:
            clean_ts = timestamp.replace("Z", "").split(".")[0]
            dt = datetime.fromisoformat(clean_ts)
        return dt.strftime("%Y-%m-%d %I:%M %p") 
    except:
        return str(timestamp)

# --- Tracking Logic (Same as before) ---

def track_uniuni(tracking_number, full_history=False):
    # [Logic Unchanged from previous working version]
    # Re-pasting for completeness of file
    API_KEY = "SMq45nJhQuNR3WHsJA6N" 
    url = "https://delivery-api.uniuni.ca/cargo/trackinguniuninew"
    params = {"id": tracking_number, "key": API_KEY}
    headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json", "Origin": "https://www.uniuni.com", "Referer": "https://www.uniuni.com/"}

    try:
        response = requests.get(url, params=params, headers=headers, timeout=20)
        if response.status_code != 200: return {"status": f"HTTP {response.status_code}", "details": "Error", "events": []}
        try: data = response.json()
        except: return {"status": "Parse Error", "details": "Invalid JSON", "events": []}
        
        valid_list = data.get("data", {}).get("valid_tno", [])
        if not valid_list: return {"status": "No Data", "details": "Not found", "events": []}
        
        events = valid_list[0].get("spath_list", [])
        if not events: return {"status": "Label Created", "details": "No scans", "events": []}
        
        latest = events[0]
        desc = latest.get("pathInfo") or latest.get("code") or "Update"
        loc = latest.get("pathAddr") or latest.get("pathAddress") or ""
        time_str = format_time(latest.get("pathTime"), is_unix=True)
        
        status_text = desc
        if loc and loc not in desc: status_text += f" ({loc})"
        full_details = f"{status_text} @ {time_str}" if time_str else status_text
        status_header = "Delivered" if "delivered" in desc.lower() else "Active"

        formatted_events = []
        if full_history:
            for e in events:
                e_time = format_time(e.get("pathTime"), is_unix=True)
                line = f"🕒 *{e_time}*\n└ {e.get('pathInfo') or e.get('code')}"
                if e.get('pathAddr'): line += f" ({e.get('pathAddr')})"
                formatted_events.append(line)

        return {"status": status_header, "details": full_details, "events": formatted_events}
    except Exception as e: return {"status": "Error", "details": str(e), "events": []}

def get_fedex_session():
    if not FEDEX_CLIENT_ID or not FEDEX_CLIENT_SECRET: return None, None
    envs = [{"url": "https://apis.fedex.com", "auth": "/oauth/token"}, {"url": "https://apis-sandbox.fedex.com", "auth": "/oauth/token"}]
    for env in envs:
        try:
            r = requests.post(env['url'] + env['auth'], data={"grant_type": "client_credentials", "client_id": FEDEX_CLIENT_ID, "client_secret": FEDEX_CLIENT_SECRET}, timeout=10)
            if r.status_code == 200: return r.json().get("access_token"), env['url']
        except: pass
    return None, None

def track_fedex(tracking_number, full_history=False):
    token, base_url = get_fedex_session()
    if not token: return {"status": "Auth Error", "details": "Check Keys", "events": []}

    url = f"{base_url}/track/v1/trackingnumbers"
    payload = {"trackingInfo": [{"trackingNumberInfo": {"trackingNumber": tracking_number}}], "includeDetailedScans": True}
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {token}"}

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=15)
        if response.status_code != 200: return {"status": "API Error", "details": f"HTTP {response.status_code}", "events": []}
        
        results = response.json().get("output", {}).get("completeTrackResults", [])
        if not results: return {"status": "No Data", "details": "Not found", "events": []}
        
        track_result = results[0].get("trackResults", [])[0]
        if track_result.get("error"): return {"status": "Error", "details": track_result.get("error").get("message"), "events": []}

        latest = track_result.get("latestStatusDetail", {})
        scan_events = track_result.get("scanEvents", [])
        
        time_str = format_time(scan_events[0].get("date", "")) if scan_events else ""
        desc = latest.get("description", "In Transit")
        loc_str = f"{latest.get('scanLocation', {}).get('city', '')}, {latest.get('scanLocation', {}).get('stateOrProvinceCode', '')}".strip(", ")
        
        detail_text = f"{desc} ({loc_str}) @ {time_str}" if loc_str else f"{desc} @ {time_str}"
        header = "Delivered" if "delivered" in desc.lower() else "Active"

        formatted_events = []
        if full_history:
            for e in scan_events:
                e_time = format_time(e.get("date", ""))
                line = f"🕒 *{e_time}*\n└ {e.get('eventDescription')}"
                if e.get('scanLocation', {}).get('city'): line += f" ({e.get('scanLocation', {}).get('city')})"
                formatted_events.append(line)

        return {"status": header, "details": detail_text, "events": formatted_events}
    except Exception as e: return {"status": "Error", "details": str(e), "events": []}

# --- Multi-User Actions ---

def get_tracker(number):
    u_num = number.upper()
    if u_num.isdigit() and len(u_num) in [12, 15, 20, 22]: return track_fedex, "FedEx"
    return track_uniuni, "UniUni"

def perform_check(force_report=False, specific_user_id=None):
    """
    Checks packages. 
    If specific_user_id is set, only check that user (Manual Refresh).
    Otherwise, check ALL users (Scheduled Cron).
    """
    data = load_data()
    users = data.get("users", {})
    
    # Identify which users to process
    target_users = [specific_user_id] if specific_user_id else list(users.keys())
    
    updates_found = False
    
    for user_id in target_users:
        user_id = str(user_id) # Ensure key is string
        packages = users.get(user_id, [])
        
        if not packages and specific_user_id:
            send_telegram_message(user_id, "📭 **Tracking List is Empty**", [[{"text": "🔙 Main Menu", "callback_data": "main_menu"}]])
            continue

        report_lines = []
        history_buttons = []
        user_updated = False

        for pkg in packages:
            num = pkg['number']
            tracker_func, carrier_name = get_tracker(num)
            
            result = tracker_func(num, full_history=False)
            current_details = result['details']
            
            is_changed = current_details != pkg.get('last_details', '')
            
            if is_changed:
                user_updated = True
                updates_found = True
                pkg['last_status'] = result['status']
                pkg['last_details'] = current_details

            # Generate Report Line if Changed OR Forced
            if is_changed or force_report:
                icon = "🟢" if is_changed else "📦"
                detail_view = current_details[:150] + "..." if len(current_details) > 150 else current_details
                line = f"{icon} *{carrier_name}*: `{num}`\n{detail_view}"
                report_lines.append(line)
                history_buttons.append([{"text": f"📜 History: {num}", "callback_data": f"history_{num}"}])

        if report_lines:
            header = "*🔔 Status Updates*" if not force_report else "*📋 Full Tracking Report*"
            full_message = f"{header}\n\n" + "\n\n".join(report_lines)
            all_buttons = history_buttons + [[{"text": "🔄 Refresh Again", "callback_data": "refresh"}], [{"text": "🔙 Main Menu", "callback_data": "main_menu"}]]
            send_telegram_message(user_id, full_message, all_buttons)

    if updates_found:
        save_data(data)
    
    return updates_found

def send_history(number, user_id):
    tracker_func, carrier_name = get_tracker(number)
    result = tracker_func(number, full_history=True)
    events = result.get("events", [])
    
    if not events: msg = f"📜 *History for {carrier_name}* `{number}`\n\n_No history found._"
    else:
        if len(events) > 15: events = events[:15] + ["... (older events truncated)"]
        msg = f"📜 *History for {carrier_name}* `{number}`\n\n" + "\n\n".join(events)

    send_telegram_message(user_id, msg, [[{"text": "🔙 Main Menu", "callback_data": "main_menu"}]])
    return False

# --- Main Entry Point ---

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["check", "add", "delete", "history"], required=True)
    parser.add_argument("--number")
    parser.add_argument("--force", action="store_true")
    # NEW ARGUMENT: CHAT_ID
    parser.add_argument("--user_id", help="The Telegram Chat ID of the user triggering the action")
    
    args = parser.parse_args()
    
    changed = False

    # 1. Scheduled Check (No specific User ID passed)
    if args.mode == "check" and not args.user_id:
        changed = perform_check(force_report=args.force)

    # 2. Manual Refresh (Specific User)
    elif args.mode == "check" and args.user_id:
        changed = perform_check(force_report=args.force, specific_user_id=args.user_id)

    # 3. Add Package (Requires User ID)
    elif args.mode == "add" and args.number and args.user_id:
        data = load_data()
        user_id = str(args.user_id)
        # Ensure user list exists
        if user_id not in data["users"]: data["users"][user_id] = []
        
        user_pkgs = data["users"][user_id]
        num = args.number.strip()
        
        if not any(p['number'] == num for p in user_pkgs):
            user_pkgs.append({"number": num, "last_status": "New"})
            save_data(data)
            send_telegram_message(user_id, f"✅ **Added:** `{num}`", [[{"text": "🔙 Main Menu", "callback_data": "main_menu"}]])
            changed = True
        else:
            send_telegram_message(user_id, f"⚠️ `{num}` is already in your list.", [[{"text": "🔙 Main Menu", "callback_data": "main_menu"}]])

    # 4. Delete Package (Requires User ID)
    elif args.mode == "delete" and args.number and args.user_id:
        data = load_data()
        user_id = str(args.user_id)
        if user_id in data["users"]:
            user_pkgs = data["users"][user_id]
            orig_len = len(user_pkgs)
            data["users"][user_id] = [p for p in user_pkgs if p['number'] != args.number]
            
            if len(data["users"][user_id]) < orig_len:
                save_data(data)
                send_telegram_message(user_id, f"🗑️ **Deleted:** `{args.number}`", [[{"text": "🔙 Main Menu", "callback_data": "main_menu"}]])
                changed = True
            else:
                send_telegram_message(user_id, f"⚠️ Number not found.", [[{"text": "🔙 Main Menu", "callback_data": "main_menu"}]])

    # 5. History (Requires User ID)
    elif args.mode == "history" and args.number and args.user_id:
        send_history(args.number, args.user_id)

    set_github_output("UPDATED", str(changed).lower())
