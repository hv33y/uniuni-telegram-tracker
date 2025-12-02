import os
import json
import requests
import logging
import argparse

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
    # Use GITHUB_OUTPUT for modern GitHub Actions runners
    output_path = os.environ.get("GITHUB_OUTPUT")
    if output_path:
        with open(output_path, "a") as f:
            f.write(f"{name}={value}\n")
    else:
        # Fallback for local testing or older runners (though deprecated)
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
# NOTE: These are placeholder functions. You must implement the real API/scraper logic here.

def track_uniuni(tracking_number):
    """Placeholder for UniUni tracking."""
    return {
        "status": "In Transit (Mock)", 
        "details": "Tracking check simulated.",
        "url": f"https://www.uniuni.com/tracking/?tracking_number={tracking_number}"
    }

def track_fedex(tracking_number):
    """Placeholder for FedEx tracking."""
    # This is the future section you requested!
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
        last_status = pkg.get('last_status')

        # 1. Determine Carrier based on naming convention
        if num.upper().startswith("UN") or "UNI" in num.upper() or num.startswith("JY"):
            result = track_uniuni(num)
            carrier = "UniUni"
        else:
            result = track_fedex(num)
            carrier = "FedEx" # Ready for your future implementation

        current_status = result['status']

        # 2. Check for changes
        is_changed = current_status != last_status
        
        if is_changed:
            updates_found = True
            pkg['last_status'] = current_status
            pkg['last_details'] = result['details']

        # 3. Build Report Line (if changed OR if forced)
        if is_changed or force_report:
            icon = "🟢" if is_changed else "📦"
            line = f"{icon} *{carrier}*: `{num}`\nStatus: {current_status}"
            report_lines.append(line)

    # 4. Save if data changed
    if updates_found:
        save_data(data)

    # 5. Send Telegram Notification
    if report_lines:
        header = "*🔔 Status Updates*" if not force_report else "*📋 Full Tracking Report*"
        full_message = f"{header}\n\n" + "\n\n".join(report_lines)
        
        # Add a refresh button for convenience
        buttons = [[{"text": "🔄 Refresh Again", "callback_data": "refresh"}]]
        send_telegram_message(full_message, buttons)

    return updates_found

# --- Management Logic ---

def add_package(number):
    data = load_data()
    # Check if exists
    if any(p['number'] == number for p in data['packages']):
        send_telegram_message(f"⚠️ Tracking number `{number}` is already in your list.")
        return False

    new_pkg = {
        "number": number,
        "last_status": "New",
        "last_details": "Just added"
    }
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
    
    # Filter out the number
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
    parser.add_argument("--mode", choices=["check", "add", "delete"], required=True, help="Action to perform")
    parser.add_argument("--number", help="Tracking number for add/delete")
    parser.add_argument("--force", action="store_true", help="Force sending a report even if no changes")
    
    args = parser.parse_args()
    
    changed = False

    if args.mode == "check":
        changed = perform_check(force_report=args.force)
    
    elif args.mode == "add":
        if args.number:
            changed = add_package(args.number)
        else:
            logging.error("No number provided for add mode")
            
    elif args.mode == "delete":
        if args.number:
            changed = delete_package(args.number)
        else:
            logging.error("No number provided for delete mode")

    # Output result for GitHub Actions
    set_github_output("UPDATED", str(changed).lower())
