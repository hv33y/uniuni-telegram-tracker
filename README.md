# UniUni Tracker Bot (Modular & Telegram Notifications)

A modular GitHub Actions bot that tracks UniUni packages (and future couriers) and sends **instant Telegram notifications only when the status changes**.  

---

## 🚀 Features

- Tracks UniUni packages (HTML scraping, no API required).  
- Only notifies when a package status changes — no duplicate messages.  
- Fully modular — easy to add FedEx, UPS, DHL, or any courier later.  
- Runs automatically on GitHub Actions every 30 minutes.  
- Lightweight: stores previous statuses in `status.json`.  
- Free, no Gmail or paid API required.  

---

## ⚡ Setup Instructions

### 1️⃣ Fork or clone the repository

### 2️⃣ Create a Telegram Bot
1. Open Telegram and search for `@BotFather`.  
2. Send `/newbot` and follow the prompts.  
3. Save your **bot token**.  

### 3️⃣ Get Your Chat ID
1. Start a chat with your bot and send `/start`.  
2. Open in browser: `https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates`.  
3. Copy the `"chat":{"id":123456789,...}` value — this is your chat ID.  

### 4️⃣ Add GitHub Secrets
Go to **Settings → Secrets → Actions** in your repository and add:

| Secret Name           | Value                                           |
|----------------------|------------------------------------------------|
| `TRACKING_NUMBERS`    | Comma-separated UniUni tracking numbers        |
| `TELEGRAM_BOT_TOKEN`  | Your Telegram bot token                        |
| `TELEGRAM_CHAT_ID`    | Your chat ID from step 3                        |

---

### 5️⃣ Test the Workflow
1. Go to **Actions → Workflow Dispatch → Run workflow**.  
2. Check your Telegram — you should receive a notification if any status changes.  

---

### 6️⃣ GitHub Actions Scheduling
The workflow runs automatically every 30 minutes by default. You can adjust this by editing `.github/workflows/track.yml`:

```yaml
cron: "*/30 * * * *"  # every 30 minutes
