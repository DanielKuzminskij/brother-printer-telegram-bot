# Brother Printer Telegram Bot

This Telegram bot automatically retrieves and reports printer usage data from Brother's Refresh EZ Print Subscription service. It handles login via Playwright, securely manages tokens and cookies, and sends printer status updates directly to your Telegram account.

## 📌 Features

- **Automatic login** using Playwright.
- **Session persistence** with tokens and cookies stored securely.
- **Telegram integration** for quick status updates.
- **Automatic token renewal** upon expiry.

## 🛠 Prerequisites

- Python 3.9+
- Playwright
- aiohttp
- python-telegram-bot
- requests

## 🔧 Installation

```bash
git clone https://github.com/DanielKuzminskij/brother-printer-telegram-bot.git
cd brother-printer-telegram-bot
pip install -r requirements.txt
playwright install chromium
```

## ⚙ Configuration

Update credentials and tokens in `printer_bot.py`:

```python
EMAIL = "your_email@example.com"
PASSWORD = "your_password"
BOT_TOKEN = "your_telegram_bot_token"
AUTHORIZED_USER_ID = your_telegram_user_id
```

## 🚀 Running the Bot

```bash
python printer_bot.py
```

## 🤖 Telegram Commands

- `/status` - Retrieves the latest printer status.

## 🗃 Project Structure

```plaintext
brother-printer-telegram-bot/
└── brother-bot/
    └── printer_bot.py
└── README.md
└── requirements.txt
```

## ⚠️ Security

- **Do not share** your `.token`, `.cookies`, or credentials publicly.
- Ensure your repository is private or sensitive files are in `.gitignore`.
