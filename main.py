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
ADMIN_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID") 
FEDEX_CLIENT_ID = os.environ.get("FEDEX_CLIENT_ID")
FEDEX_CLIENT_SECRET = os.environ.get("FEDEX_CLIENT_SECRET")
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

def send_telegram_message(chat_id, message, buttons=None):
    if not TELEGRAM_BOT_TOKEN or not chat_id: return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": message, "parse_mode": "Markdown", "disable_web_page_preview": True}
    if buttons: payload["reply_markup"] = {"inline_keyboard": buttons}
    try: requests.post(url, json=payload).raise_for_status()
    except Exception as e: logging.error(f"Telegram Error for {chat_id}: {e}")

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

# --- UNIUNI TRACKING ---
def track_uniuni(tracking_number, full_history=False):
    API_KEY = "SMq45nJhQuNR3WHsJA6N" 
    url = "https://delivery-api.uniuni.ca/cargo/trackinguniuninew"
    params = {"id": tracking_number, "key": API_KEY}
    tracking_url = f"https://www.uniuni.com/tracking/?tracking_number={tracking_number}"
    
    headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json", "Origin": "https://www.uniuni.com", "Referer": "https://www.uniuni.com/"}
    try:
        response = requests.get(url, params=params, headers=headers, timeout=20)
        if response.status_code != 200: return {"status": f"HTTP {response.status_code}", "details": "Error", "events": [], "url": tracking_url}
        try: data = response.json()
        except: return {"status": "Parse Error", "details": "Invalid JSON", "events": [], "url": tracking_url}
        
        valid_list = data.get("data", {}).get("valid_tno", [])
        if not valid_list: return {"status": "No Data", "details": "Not found", "events": [], "url": tracking_url}
        
        events = valid_list[0].get("spath_list", [])
        if not events: return {"status": "Label Created", "details": "No scans", "events": [], "url": tracking_url}
        
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
        return {"status": status_header, "details": full_details, "events": formatted_events, "url": tracking_url}
    except Exception as e: return {"status": "Error", "details": str(e), "events": [], "url": tracking_url}

# --- FEDEX TRACKING ---
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
    tracking_url = f"https://www.fedex.com/fedextrack/?trknbr={tracking_number}"
    token, base_url = get_fedex_session()
    if not token: return {"status": "Auth Error", "details": "Check Keys", "events": [], "url": tracking_url}

    url = f"{base_url}/track/v1/trackingnumbers"
    payload = {"trackingInfo": [{"trackingNumberInfo": {"trackingNumber": tracking_number}}], "includeDetailedScans": True}
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {token}"}

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=15)
        if response.status_code != 200: return {"status": "API Error", "details": f"HTTP {response.status_code}", "events": [], "url": tracking_url}
        results = response.json().get("output", {}).get("completeTrackResults", [])
        if not results: return {"status": "No Data", "details": "Not found", "events": [], "url": tracking_url}
        track_result = results[0].get("trackResults", [])[0]
        if track_result.get("error"): return {"status": "Error", "details": track_result.get("error").get("message"), "events": [], "url": tracking_url}
        
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
        return {"status": header, "details": detail_text, "events": formatted_events, "url": tracking_url}
    except Exception as e: return {"status": "Error", "details": str(e), "events": [], "url": tracking_url}

# --- UPS TRACKING (LINK MODE) ---
def track_ups(tracking_number, full_history=False):
    # Free mode: UPS blocks scrapers, so we provide a direct link.
    tracking_url = f"https://www.ups.com/track?loc=en_US&tracknum={tracking_number}"
    return {
        "status": "UPS Tracking",
        "details": "Click tracking number to view status",
        "events": [],
        "url": tracking_url
    }

# --- CONTROLLER ---
def get_tracker(number):
    u_num = number.upper()
    if u_num.startswith("1Z"): return track_ups, "UPS"
    if u_num.isdigit() and len(u_num) in [12, 15, 20, 22]: return track_fedex, "FedEx"
    return track_uniuni, "UniUni"

def perform_check(force_report=False, specific_user_id=None):
    data = load_data()
    users = data.get("users", {})
    target_users = [specific_user_id] if specific_user_id else list(users.keys())
    updates_found = False
    
    for user_id in target_users:
        user_id = str(user_id)
        packages = users.get(user_id, [])
        if not packages and specific_user_id:
            send_telegram_message(user_id, "📭 **Tracking List is Empty**", [[{"text": "🔙 Main Menu", "callback_data": "main_menu"}]])
            continue

        report_lines = []
        history_buttons = []
        for pkg in packages:
            num = pkg['number']
            tracker_func, carrier_name = get_tracker(num)
            result = tracker_func(num, full_history=False)
            
            current_details = result['details']
            is_changed = current_details != pkg.get('last_details', '')
            
            # For UPS (Link Mode), status never changes automatically, so we rely on force_report
            if is_changed:
                updates_found = True
                pkg['last_status'] = result['status']
                pkg['last_details'] = current_details

            if is_changed or force_report:
                icon = "🟢" if is_changed else "📦"
                detail_view = current_details[:150] + "..." if len(current_details) > 150 else current_details
                
                # Make the Tracking Number a CLICKABLE LINK
                link = result.get('url', '')
                num_display = f"[{num}]({link})" if link else f"`{num}`"
                
                line = f"{icon} *{carrier_name}*: {num_display}\n{detail_view}"
                report_lines.append(line)
                
                # Only add History button if the carrier supports it (UniUni/FedEx)
                if carrier_name != "UPS":
                    history_buttons.append([{"text": f"📜 History: {num}", "callback_data": f"history_{num}"}])

        if report_lines:
            header = "*🔔 Status Updates*" if not force_report else "*📋 Full Tracking Report*"
            full_message = f"{header}\n\n" + "\n\n".join(report_lines)
            all_buttons = history_buttons + [[{"text": "🔄 Refresh Again", "callback_data": "refresh"}], [{"text": "🔙 Main Menu", "callback_data": "main_menu"}]]
            send_telegram_message(user_id, full_message, all_buttons)

    if updates_found: save_data(data)
    return updates_found

def send_history(number, user_id):
    tracker_func, carrier_name = get_tracker(number)
    result = tracker_func(number, full_history=True)
    events = result.get("events", [])
    if not events: msg = f"📜 *History for {carrier_name}* `{number}`\n\n_No history found or not supported for this carrier._"
    else:
        if len(events) > 15: events = events[:15] + ["... (older events truncated)"]
        msg = f"📜 *History for {carrier_name}* `{number}`\n\n" + "\n\n".join(events)
    send_telegram_message(user_id, msg, [[{"text": "🔙 Main Menu", "callback_data": "main_menu"}]])
    return False

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["check", "add", "delete", "history"], required=True)
    parser.add_argument("--number")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--user_id")
    args = parser.parse_args()
    
    changed = False
    if args.mode == "check": changed = perform_check(force_report=args.force, specific_user_id=args.user_id)
    elif args.mode == "history" and args.number and args.user_id: send_history(args.number, args.user_id)
    elif args.mode == "add" and args.number and args.user_id:
        data = load_data()
        user_id = str(args.user_id)
        if user_id not in data["users"]: data["users"][user_id] = []
        if not any(p['number'] == args.number.strip() for p in data["users"][user_id]):
            data["users"][user_id].append({"number": args.number.strip(), "last_status": "New"})
            save_data(data)
            send_telegram_message(user_id, f"✅ **Added:** `{args.number.strip()}`", [[{"text": "🔙 Main Menu", "callback_data": "main_menu"}]])
            changed = True
        else: send_telegram_message(user_id, f"⚠️ Exists.", [[{"text": "🔙 Main Menu", "callback_data": "main_menu"}]])
    elif args.mode == "delete" and args.number and args.user_id:
        data = load_data()
        user_id = str(args.user_id)
        if user_id in data["users"]:
            orig = len(data["users"][user_id])
            data["users"][user_id] = [p for p in data["users"][user_id] if p['number'] != args.number]
            if len(data["users"][user_id]) < orig:
                save_data(data)
                send_telegram_message(user_id, f"🗑️ **Deleted:** `{args.number}`", [[{"text": "🔙 Main Menu", "callback_data": "main_menu"}]])
                changed = True
            else: send_telegram_message(user_id, f"⚠️ Not found.", [[{"text": "🔙 Main Menu", "callback_data": "main_menu"}]])

    set_github_output("UPDATED", str(changed).lower())
