import json
import requests
import aiohttp
from playwright.async_api import async_playwright
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# URLs for Brother services
LOGIN_PAGE = "https://refreshezprintsubscription.brother-usa.com/Account/#/account/login?sessionlogout=logout"
DEVICE_URL = "https://refreshezprintsubscription.brother-usa.com/api/device/getdevicelist?checkSwap=false"

# Credentials and tokens from https://refreshezprintsubscription.brother-usa.com/Account/#/
EMAIL = "your_email@example.com"
PASSWORD = "your_password"

TOKEN_FILE = ".token"
COOKIE_FILE = ".cookies"

# Telegram bot configuration
BOT_TOKEN = "your_telegram_bot_token"
AUTHORIZED_USER_ID = 123456789 # from https://t.me/userinfobot

def save_token(token):
    with open(TOKEN_FILE, "w") as f:
        f.write(token)

def load_token():
    try:
        with open(TOKEN_FILE, "r") as f:
            return f.read().strip()
    except FileNotFoundError:
        return None

# Function to send messages via Telegram
async def send_telegram_message(text: str):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": AUTHORIZED_USER_ID, "text": text, "parse_mode": "Markdown"}
    async with aiohttp.ClientSession() as session:
        await session.post(url, data=payload)

# Function to log in and obtain token and cookies
async def browser_login_and_get_token_and_cookies():
    await send_telegram_message("🔐 *Logging in to Brother website...*")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        token_holder = {"token": None}

        async def handle_request(request):
            auth = request.headers.get("authorization")
            if auth and auth.startswith("Bearer "):
                token_holder["token"] = auth.split("Bearer ")[1]

        page.on("request", handle_request)

        await page.goto(LOGIN_PAGE)
        await page.fill('input[type="email"]', EMAIL)
        await page.fill('input[type="password"]', PASSWORD)
        await page.click('button[type="submit"]')
        await page.wait_for_timeout(6000)

        token = token_holder["token"]
        if not token:
            await send_telegram_message("❌ *Failed to retrieve token.*")
            raise Exception("Failed to retrieve Bearer Token")

        cookies = await context.cookies()
        cookie_str = "; ".join([f"{c['name']}={c['value']}" for c in cookies])
        await browser.close()

        save_token(token)
        with open(COOKIE_FILE, "w") as f:
            f.write(cookie_str)

        await send_telegram_message("✅ *Token and cookies successfully retrieved and saved.*")

        return token, cookie_str

# Retrieve device data from Brother API
async def get_device_data(token, cookie_str):
    headers = {
        "Authorization": f"Bearer {token}",
        "Cookie": cookie_str
    }
    response = requests.get(DEVICE_URL, headers=headers)

    if response.status_code == 401:
        token, cookie_str = await browser_login_and_get_token_and_cookies()
        headers["Authorization"] = f"Bearer {token}"
        headers["Cookie"] = cookie_str
        response = requests.get(DEVICE_URL, headers=headers)

    response.raise_for_status()
    return response.json()

# Build the status message for Telegram
async def build_status_message():
    token = load_token()
    cookie_str = ""
    try:
        with open(COOKIE_FILE, "r") as f:
            cookie_str = f.read().strip()
    except FileNotFoundError:
        pass

    if not token or not cookie_str:
        token, cookie_str = await browser_login_and_get_token_and_cookies()

    data = await get_device_data(token, cookie_str)
    device = data["deviceGroupViewModels"][0]["devices"][0]
    usage = device["service"]["currentUsage"]
    plan = device["service"]["currentPlan"]

    message = (
        f"📠 *Printer:* {device['model']} ({device['serialNumber']})\n"
        f"📅 *Period:* {usage['usageCycleStartDate']} → {usage['usageCycleEndDate']}\n"
        f"✅ *Plan limit:* {plan['planPages']} pages\n"
        f"🔁 *Rollover:* {usage['givenRolloverPages']} pages\n"
        f"🖨️ *Printed:* {usage['printedTotalPages']} pages"
    )
    return message

# Telegram command handler for '/status'
async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != AUTHORIZED_USER_ID:
        await update.message.reply_text("⛔ Access denied.")
        return

    await update.message.reply_text("⏳ Collecting data...")
    try:
        msg = await build_status_message()
        await update.message.reply_text(msg, parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")

# Bot startup
if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("status", status))
    print("🤖 Bot is running. Send /status")
    app.run_polling()
