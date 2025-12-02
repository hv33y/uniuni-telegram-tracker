# Modular Package Tracking Bot with Telegram Notifications

This project is a modular GitHub Actions bot for tracking UniUni packages, designed to be extended to other couriers such as FedEx or UPS. The bot sends instant Telegram notifications when a tracking status changes. It stores previous statuses to prevent duplicate notifications and allows dynamic management of tracking numbers directly through the GitHub Actions interface.

---

## Overview

The bot is fully modular. Each courier can have its own tracker module in the `trackers/` directory. The current implementation tracks UniUni packages. The system stores previous statuses in `status.json` to ensure notifications are sent only when the status changes. 

Tracking numbers can be added or removed dynamically using the workflow dispatch inputs, so manual editing of secrets is not required after setup.

---

## Setup Instructions

Fork or clone the repository to your GitHub account.

### Create a Telegram Bot

1. Open Telegram and start a chat with `@BotFather`.
2. Use `/newbot` to create a new bot. Follow the prompts to obtain a bot token.
3. Send a message to your bot and obtain your chat ID using `https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates`.

### Add GitHub Secrets

Go to **Settings → Secrets → Actions** and add the following secrets:

- `TELEGRAM_BOT_TOKEN` — your bot token from BotFather.
- `TELEGRAM_CHAT_ID` — your Telegram chat ID.
- `GITHUB_TOKEN` — automatically available in workflows, used for committing updated statuses.

---

## Running the Workflow

The GitHub Actions workflow is configured to run automatically every 30 minutes. It can also be triggered manually using the workflow dispatch interface, which supports two inputs:

- `add_tracking` — enter a tracking number to add to the bot. It will be saved permanently in `status.json`.
- `stop_tracking` — enter a tracking number to remove it permanently from tracking.

The bot will check all tracking numbers in `status.json` and send Telegram notifications for any changes.

---

## Workflow Structure

- `main.py` — core script that handles tracking, status comparison, and Telegram notifications.
- `trackers/` — directory for individual courier tracker modules. Each module should implement a `get_status(tracking_number)` function returning `(status, checkpoint)`.
- `status.json` — stores tracking numbers, their assigned tracker module, and last known status.
- `.github/workflows/track.yml` — GitHub Actions workflow that schedules periodic checks and supports workflow dispatch inputs.
- `requirements.txt` — Python dependencies.

---

## Extending to Additional Couriers

To add a new courier:

1. Create a new module in the `trackers/` directory, e.g., `fedex.py`.
2. Implement a `get_status(tracking_number)` function that returns `(status, checkpoint)`.
3. Update `TRACKER_MAPPING` in `main.py` to assign tracking numbers to the new tracker module.

No other changes are required in the workflow or notification system.

---

## Key Features

- Modular design for multiple couriers.
- Only notifies on status changes to avoid duplicate messages.
- Telegram notifications provide instant updates to any device.
- Dynamic management of tracking numbers via workflow inputs.
- Fully automated with GitHub Actions.
