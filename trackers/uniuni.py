import requests
import re
import json

def get_status(tracking_number):
    """
    Returns (status, checkpoint) for a UniUni tracking number
    """
    url = f"https://portal.uniuni.com/track/{tracking_number}"
    r = requests.get(url, timeout=10)
    html = r.text

    match = re.search(r"window\.__NUXT__=(\{.*\});", html)
    if not match:
        raise Exception("Failed to extract UniUni data")

    data = json.loads(match.group(1))
    item = data["state"]["track"]["items"][0]
    status = item["status"]
    checkpoint = item.get("lastEvent", "")
    return status, checkpoint
