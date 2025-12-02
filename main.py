import os
import json
import requests
import logging
import argparse
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Configuration from Environment Variables
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
DATA_FILE = "tracking.json"

def load_data():
    """Loads the list of packages from the JSON file."""
    if not os.path.exists(DATA_FILE):
        return {"packages": []}
    try:
        with open(DATA_FILE, 'r') as f:
            return json.load(f)
    except json.JSONDecodeError:
        logging.warning(f"Error decoding {DATA_FILE}. Returning empty list.")
        return {"packages": []}

def save_data(data):
    """Saves the updated list back to the JSON file."""
    try:
        with open(DATA_FILE, 'w') as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logging.error(f"Failed to save data to {DATA_FILE}: {e}")

def set_github_output(name, value):
    """Sets an output variable for GitHub Actions."""
    output_path = os.environ.get("GITHUB_OUTPUT")
    if output_path:
        with open(output_path, "a") as f:
            f.write(f"{name}={value}\n")
    else:
        print(f"::set-output name={name}::{value}")

def send_telegram_message(message, buttons=None):
    """Sends a message to Telegram."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logging.error("Telegram credentials missing.")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }

    if buttons:
        payload["reply_markup"] = {"inline_keyboard": buttons}

    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
    except Exception as e:
        logging.error(f"Failed to send Telegram message: {e}")

# --- Tracking Logic ---

def track_uniuni(tracking_number):
    """
    Fetches REAL tracking data from UniUni.
    """
    url = f"https://t.uniuni.com/api/v1/tracking/{tracking_number}"
    tracking_url = f"https://www.uniuni.com/tracking/?tracking_number={tracking_number}"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Accept": "application/json",
        "Referer": "https://www.uniuni.com/"
    }

    try:
        response = requests.get(url, headers=headers, timeout=15)
        
        if response.status_code == 200:
            data = response.json()
            
            # Note: The structure of data varies. We check typical fields.
            # Assuming data structure: { "code": "200", "data": { "tracks": [...], "status": "..." } }
            
            if data.get("code") != "200" and data.get("code") != 200:
                 return {
                    "status": "Check Website",
                    "details": "Tracking info not found or restricted.",
                    "url": tracking_url
                }

            # Parse the specific 'data' payload
            payload = data.get("data", {})
            tracks = payload.get("tracks", [])
            
            if not tracks:
                return {
                    "status": "Label Created",
                    "details": "No scanning events yet.",
                    "url": tracking_url
                }

            # Get the most recent event (usually first or last in list, we sort to be safe)
            # UniUni usually returns reverse chronological, but let's verify.
            # We assume index 0 is latest if sorted desc, but let's just grab the first one provided.
            latest_event = tracks[0] 
            
            description = latest_event.get("scanType", "Update")
            location = latest_event.get("scanCity", "")
            timestamp = latest_event.get("scanTime", "")

            status_text = f"{description}"
            if location:
                status_text += f" ({location})"
            
            return {
                "status": "Active", # Simplified status
                "details": f"{status_text} @ {timestamp}",
                "url": tracking_url
            }

        else:
            return {
                "status": f"HTTP {response.status_code}",
                "details": "Could not connect to UniUni API.",
                "url": tracking_url
            }

    except Exception as e:
        logging.error(f"UniUni Scan Error: {e}")
        return {
            "status": "Error",
            "details": "Failed to parse tracking data.",
            "url": tracking_url
        }

def track_fedex(tracking_number):
    """Placeholder for FedEx tracking."""
    return {
        "status": "Pending (FedEx Ready)",
        "details": "FedEx integration pending.",
        "url": f"https://www.fedex.com/fedextrack/?trknbr={tracking_number}"
    }

def perform_check(force_report=False):
    """Checks all packages and alerts on changes or force report."""
    data = load_data()
    packages = data.get("packages", [])
    
    if not packages:
        if force_report:
            send_telegram_message("📭 **Tracking List is Empty**\n\nUse the menu to add tracking numbers.")
        return False

    updates_found = False
    report_lines = []

    for pkg in packages:
        num = pkg['number']
        last_details = pkg.get('last_details', '')
        u_num = num.upper()

        # --- CARRIER DETECTION ---
        # Logic: FedEx tracking numbers are usually purely numeric (12, 15, 20, or 22 digits).
        # Default to UniUni since it's the primary tracker, unless it looks strictly like FedEx.
        
        if u_num.isdigit() and len(u_num) in [12, 15, 20, 22]:
            result = track_fedex(num)
            carrier = "FedEx"
        else:
            result = track_uniuni(num)
            carrier = "UniUni"

        current_details = result['details']
        
        # Compare DETAILS instead of just status, as 'In Transit' might stay the same 
        # but the location/time updates.
        is_changed = current_details != last_details
        
        if is_changed:
            updates_found = True
            pkg['last_status'] = result['status']
            pkg['last_details'] = current_details

        # Build Report Line
        if is_changed or force_report:
            icon = "🟢" if is_changed else "📦"
            
            # Format the detail text to be clean
            detail_text = current_details
            if len(detail_text) > 100:
                detail_text = detail_text[:97] + "..."

            line = f"{icon} *{carrier}*: `{num}`\n{detail_text}"
            report_lines.append(line)

    if updates_found:
        save_data(data)

    if report_lines:
        header = "*🔔 Status Updates*" if not force_report else "*📋 Full Tracking Report*"
        full_message = f"{header}\n\n" + "\n\n".join(report_lines)
        buttons = [[{"text": "🔄 Refresh Again", "callback_data": "refresh"}]]
        send_telegram_message(full_message, buttons)

    return updates_found

# --- Management Logic ---

def add_package(number):
    data = load_data()
    # Normalize input
    number = number.strip()
    
    if any(p['number'] == number for p in data['packages']):
        send_telegram_message(f"⚠️ Tracking number `{number}` is already in your list.")
        return False

    new_pkg = {"number": number, "last_status": "New", "last_details": "Just added"}
    data['packages'].append(new_pkg)
    save_data(data)
    
    send_telegram_message(
        f"✅ **Added:** `{number}`\nI will check this automatically every 30 minutes.",
        [[{"text": "🔙 Main Menu", "callback_data": "main_menu"}]]
    )
    return True

def delete_package(number):
    data = load_data()
    original_count = len(data['packages'])
    data['packages'] = [p for p in data['packages'] if p['number'] != number]

    if len(data['packages']) < original_count:
        save_data(data)
        send_telegram_message(f"🗑️ **Deleted:** `{number}`")
        return True
    else:
        send_telegram_message(f"⚠️ Could not find `{number}` to delete.")
        return False

# --- Main Entry Point ---

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["check", "add", "delete"], required=True)
    parser.add_argument("--number")
    parser.add_argument("--force", action="store_true")
    
    args = parser.parse_args()
    
    changed = False

    if args.mode == "check":
        changed = perform_check(force_report=args.force)
    elif args.mode == "add" and args.number:
        changed = add_package(args.number)
    elif args.mode == "delete" and args.number:
        changed = delete_package(args.number)

    set_github_output("UPDATED", str(changed).lower())
