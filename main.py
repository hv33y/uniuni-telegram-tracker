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
FEDEX_CLIENT_ID = os.environ.get("FEDEX_CLIENT_ID")
FEDEX_CLIENT_SECRET = os.environ.get("FEDEX_CLIENT_SECRET")
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
    Fetches REAL tracking data from UniUni using the delivery-api endpoint.
    """
    API_KEY = "SMq45nJhQuNR3WHsJA6N" 
    url = "https://delivery-api.uniuni.ca/cargo/trackinguniuninew"
    params = {"id": tracking_number, "key": API_KEY}
    tracking_url = f"https://www.uniuni.com/tracking/?tracking_number={tracking_number}"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Origin": "https://www.uniuni.com",
        "Referer": "https://www.uniuni.com/"
    }

    try:
        response = requests.get(url, params=params, headers=headers, timeout=20)
        
        if response.status_code != 200:
            return {"status": f"HTTP {response.status_code}", "details": "Server returned error.", "url": tracking_url}

        try:
            data = response.json()
        except json.JSONDecodeError:
            return {"status": "Parse Error", "details": "API returned invalid JSON.", "url": tracking_url}

        api_data = data.get("data", {})
        
        if api_data.get("invalid_tno"):
            return {"status": "Not Found", "details": "Tracking number not found in system.", "url": tracking_url}
            
        valid_list = api_data.get("valid_tno", [])
        if not valid_list:
            return {"status": "No Data", "details": "No tracking details returned.", "url": tracking_url}
            
        package_obj = valid_list[0]
        events = package_obj.get("spath_list", [])
        
        if not events:
            return {"status": "Label Created", "details": "No scan events yet.", "url": tracking_url}
            
        latest = events[0]
        description = latest.get("pathInfo") or latest.get("code") or "Update"
        location = latest.get("pathAddr") or latest.get("pathAddress") or ""
        
        timestamp_raw = latest.get("pathTime")
        time_str = ""
        if timestamp_raw:
            try:
                dt_object = datetime.fromtimestamp(timestamp_raw)
                time_str = dt_object.strftime("%Y-%m-%d %H:%M")
            except:
                pass
        
        status_text = description
        if location and location not in description:
            status_text += f" ({location})"
        
        full_details = f"{status_text} @ {time_str}" if time_str else status_text

        status_header = "Active"
        if "delivered" in description.lower():
            status_header = "Delivered"
            
        return {"status": status_header, "details": full_details, "url": tracking_url}

    except Exception as e:
        logging.error(f"UniUni Scan Error: {e}")
        return {"status": "System Error", "details": f"Script Error: {str(e)}", "url": tracking_url}

def get_fedex_token():
    """Authenticates with FedEx to get an access token."""
    if not FEDEX_CLIENT_ID or not FEDEX_CLIENT_SECRET:
        logging.error("FedEx credentials missing.")
        return None
        
    url = "https://apis.fedex.com/oauth/token"
    payload = {
        "grant_type": "client_credentials",
        "client_id": FEDEX_CLIENT_ID,
        "client_secret": FEDEX_CLIENT_SECRET
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}

    try:
        response = requests.post(url, data=payload, headers=headers, timeout=10)
        if response.status_code == 200:
            return response.json().get("access_token")
        else:
            logging.error(f"FedEx Auth Failed: {response.text}")
            return None
    except Exception as e:
        logging.error(f"FedEx Auth Error: {e}")
        return None

def track_fedex(tracking_number):
    """Fetches REAL tracking data from FedEx API."""
    tracking_url = f"https://www.fedex.com/fedextrack/?trknbr={tracking_number}"
    
    token = get_fedex_token()
    if not token:
        return {"status": "Auth Error", "details": "Could not authenticate with FedEx.", "url": tracking_url}

    url = "https://apis.fedex.com/track/v1/trackingnumbers"
    
    payload = {
        "trackingInfo": [
            {
                "trackingNumberInfo": {
                    "trackingNumber": tracking_number
                }
            }
        ],
        "includeDetailedScans": True
    }
    
    headers = {
        "Content-Type": "application/json",
        "X-locale": "en_US",
        "Authorization": f"Bearer {token}"
    }

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=15)
        
        if response.status_code != 200:
             return {"status": f"HTTP {response.status_code}", "details": "FedEx API Error.", "url": tracking_url}

        data = response.json()
        
        # Parse logic for FedEx
        output = data.get("output", {})
        complete_results = output.get("completeTrackResults", [])
        
        if not complete_results:
             return {"status": "No Data", "details": "No results found.", "url": tracking_url}

        track_result = complete_results[0].get("trackResults", [])[0]
        
        # Check for errors in the specific tracking number result
        error_info = track_result.get("error")
        if error_info:
             return {"status": "Not Found", "details": "Invalid Tracking Number.", "url": tracking_url}

        latest_status_detail = track_result.get("latestStatusDetail", {})
        scan_events = track_result.get("scanEvents", [])

        # Get status description
        status_desc = latest_status_detail.get("description", "In Transit")
        city = latest_status_detail.get("scanLocation", {}).get("city", "")
        state = latest_status_detail.get("scanLocation", {}).get("stateOrProvinceCode", "")
        
        # Get Time
        # FedEx returns dates usually like "2023-10-25T10:00:00"
        timestamp_str = ""
        if scan_events:
            timestamp_str = scan_events[0].get("date", "")
            # Try to format it cleanly
            try:
                dt = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
                timestamp_str = dt.strftime("%Y-%m-%d %H:%M")
            except:
                pass # Keep original string if parse fails

        location_str = f"{city}, {state}".strip(", ")
        
        detail_text = status_desc
        if location_str:
            detail_text += f" ({location_str})"
        if timestamp_str:
            detail_text += f" @ {timestamp_str}"

        # Determine Header Status
        header = "Active"
        if "delivered" in status_desc.lower():
            header = "Delivered"
        elif "exception" in status_desc.lower():
            header = "Exception"

        return {"status": header, "details": detail_text, "url": tracking_url}

    except Exception as e:
        logging.error(f"FedEx Scan Error: {e}")
        return {"status": "System Error", "details": f"Script Error: {str(e)}", "url": tracking_url}

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
        if u_num.isdigit() and len(u_num) in [12, 15, 20, 22]:
            result = track_fedex(num)
            carrier = "FedEx"
        else:
            result = track_uniuni(num)
            carrier = "UniUni"

        current_details = result['details']
        current_status = result['status']
        
        is_changed = current_details != last_details
        
        if is_changed:
            updates_found = True
            pkg['last_status'] = current_status
            pkg['last_details'] = current_details

        if is_changed or force_report:
            icon = "🟢" if is_changed else "📦"
            
            detail_text = current_details
            if len(detail_text) > 200:
                detail_text = detail_text[:197] + "..."

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
