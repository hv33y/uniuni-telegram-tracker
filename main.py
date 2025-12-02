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
TRACKING_NUMBERS = os.environ.get("TRACKING_NUMBERS", "").split(",")
REPO_OWNER = os.environ.get("GITHUB_REPOSITORY_OWNER") # For the refresh button link if needed

# File to store the last known state
STATUS_FILE = "tracking_status.json"

def load_status():
    if os.path.exists(STATUS_FILE):
        with open(STATUS_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_status(data):
    with open(STATUS_FILE, 'w') as f:
        json.dump(data, f, indent=2)

def send_telegram_message(message, show_refresh_button=True):
    """Sends a message to Telegram with an optional Refresh button."""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }

    if show_refresh_button:
        # This Inline Keyboard sends a callback data 'refresh' when clicked
        payload["reply_markup"] = {
            "inline_keyboard": [[
                {"text": "🔄 Refresh Status", "callback_data": "refresh"}
            ]]
        }

    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
    except Exception as e:
        logging.error(f"Failed to send Telegram message: {e}")

def track_uniuni(tracking_number):
    """
    Tracks UniUni package.
    NOTE: UniUni does not have a public documented API. 
    This attempts to use the endpoint used by their frontend.
    If this fails, you may need to inspect their website Network tab for a new endpoint.
    """
    # This is a common endpoint structure for UniUni. 
    # Alternatively, scraping https://www.uniuni.com/tracking/ might be required.
    # For now, we simulate a check or use a known public tracker API if available.
    
    # Placeholder logic for demonstration:
    # In a real scenario, you would perform a request:
    # url = f"https://api.uniuni.com/public/v1/tracking/{tracking_number}"
    # r = requests.get(url)
    # data = r.json()
    
    logging.info(f"Checking UniUni: {tracking_number}")
    
    # Since we can't hit their private API without a key reliably in this demo,
    # we will use a "manual link" strategy for the message detail, 
    # but strictly track the *check* here.
    
    # TODO: Replace with actual scraping logic if you have a specific endpoint.
    # For now, we return a dummy status to demonstrate the flow or you can implement 
    # specific scraping here using BeautifulSoup if the API is protected.
    
    return {
        "status": "Unknown (Implement API/Scraper)", 
        "details": "Could not fetch automated details.",
        "url": f"https://www.uniuni.com/tracking/?tracking_number={tracking_number}"
    }

def track_fedex(tracking_number):
    """Placeholder for future FedEx implementation."""
    return {
        "status": "Pending Implementation",
        "details": "FedEx tracking coming soon.",
        "url": f"https://www.fedex.com/fedextrack/?trknbr={tracking_number}"
    }

def main():
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logging.error("Telegram secrets missing.")
        return

    old_status = load_status()
    new_status = old_status.copy()
    updates_found = False

    for num in TRACKING_NUMBERS:
        num = num.strip()
        if not num: continue

        # Detect Carrier (Simple logic)
        if num.startswith("UN") or "UNI" in num or num.startswith("JY"):
            result = track_uniuni(num)
            carrier = "UniUni"
        else:
            result = track_fedex(num)
            carrier = "FedEx"

        # Compare with old status
        last_check = old_status.get(num, {})
        current_summary = result.get("status")

        # If status changed (or never tracked before)
        if current_summary != last_check.get("status"):
            msg = (
                f"📦 *Update for {carrier}*\n"
                f"ID: `{num}`\n"
                f"Status: *{current_summary}*\n"
                f"Details: {result.get('details')}\n\n"
                f"[Track on Website]({result.get('url')})"
            )
            send_telegram_message(msg)
            
            # Update our local state
            new_status[num] = {
                "status": current_summary,
                "timestamp": "Now" # You can add actual time here
            }
            updates_found = True
        else:
            logging.info(f"No change for {num}")

    # Save state if anything changed
    if updates_found:
        save_status(new_status)
        # We also print a special string for the GitHub Action to know it needs to commit
        print("::set-output name=UPDATED::true")
    else:
        print("::set-output name=UPDATED::false")

if __name__ == "__main__":
    main()
