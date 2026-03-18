import os
import time
import requests
import aiohttp
import asyncio
from playwright.async_api import async_playwright
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

from dotenv import load_dotenv
load_dotenv()

LOGIN_PAGE = "https://refreshezprintsubscription.brother-usa.com/Account/#/account/login?sessionlogout=logout"
DEVICE_URL = "https://refreshezprintsubscription.brother-usa.com/api/device/getdevicelist?checkSwap=false"

EMAIL = os.getenv("BROTHER_EMAIL", "")
PASSWORD = os.getenv("BROTHER_PASSWORD", "")
TOKEN_FILE = os.getenv("TOKEN_FILE", ".token")
COOKIE_FILE = os.getenv("COOKIE_FILE", ".cookies")

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
AUTHORIZED_USER_ID = int(os.getenv("AUTHORIZED_USER_ID", "0"))


def save_token(token: str) -> None:
    with open(TOKEN_FILE, "w", encoding="utf-8") as file:
        file.write(token)


def load_token() -> str | None:
    try:
        with open(TOKEN_FILE, "r", encoding="utf-8") as file:
            return file.read().strip()
    except FileNotFoundError:
        return None


async def send_telegram_message(text: str) -> None:
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": AUTHORIZED_USER_ID,
        "text": text,
        "parse_mode": "Markdown"
    }

    try:
        async with aiohttp.ClientSession() as session:
            await session.post(url, data=payload)
    except Exception as error:
        print(f"[Telegram Error] {error}")


async def send_telegram_photo(photo_path: str, caption: str | None = None) -> None:
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"

    data = aiohttp.FormData()
    data.add_field("chat_id", str(AUTHORIZED_USER_ID))

    if caption:
        data.add_field("caption", caption)
        data.add_field("parse_mode", "Markdown")

    try:
        async with aiohttp.ClientSession() as session:
            with open(photo_path, "rb") as file:
                data.add_field(
                    "photo",
                    file,
                    filename=os.path.basename(photo_path),
                    content_type="image/png"
                )
                async with session.post(url, data=data) as response:
                    if response.status != 200:
                        body = await response.text()
                        print(f"[Telegram Photo Error] HTTP {response.status}: {body}")
    except Exception as error:
        print(f"[Telegram Photo Error] {error}")


async def screenshot_and_send(page, caption: str) -> None:
    filename = f"debug_{int(time.time())}.png"
    await page.screenshot(path=filename, full_page=True)

    await send_telegram_photo(filename, caption=caption)

    try:
        os.remove(filename)
    except Exception as error:
        print(f"[Screenshot Cleanup Error] {error}")


async def browser_login_and_get_token_and_cookies():
    await send_telegram_message("🔐 *Logging in to the Brother website...*")

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        token_holder = {"token": None}

        async def handle_request(request):
            auth_header = request.headers.get("authorization")
            if auth_header and auth_header.startswith("Bearer "):
                token_holder["token"] = auth_header.split("Bearer ")[1]

        page.on("request", handle_request)

        await page.goto(LOGIN_PAGE)

        login_signup_button = page.get_by_role("button", name="LogIn/SignUp")

        if await login_signup_button.count() > 0:
            button = login_signup_button.last
            await button.scroll_into_view_if_needed()
            await button.click(timeout=30000, force=True)

        await page.wait_for_timeout(10000)
        visible_buttons = page.get_by_role("button", name="LogIn/SignUp")

        if await visible_buttons.count() > 0:
            button = visible_buttons.last
            await button.scroll_into_view_if_needed()
            await button.click(timeout=30000, force=True)

        await page.locator("#signInNamelocal").first.wait_for(state="visible", timeout=30000)
        await page.fill("#signInNamelocal", EMAIL)

        password_input = page.locator("#passwordLocal").first
        await password_input.wait_for(timeout=30000)
        await password_input.click()
        await password_input.fill(PASSWORD)

        login_button = page.locator("#btnLogin").first
        await login_button.wait_for(timeout=30000)
        await login_button.scroll_into_view_if_needed()
        await login_button.click()

        for _ in range(60):
            token = token_holder.get("token")
            if token:
                break
            await asyncio.sleep(0.5)

        token = token_holder.get("token")
        if not token:
            await send_telegram_message(
                "❌ *Failed to retrieve the Bearer token after login. It was not captured from request headers.*"
            )
            raise Exception("Failed to retrieve Bearer token from browser session")

        cookies = await context.cookies()
        cookie_string = "; ".join([f"{cookie['name']}={cookie['value']}" for cookie in cookies])

        await browser.close()

        save_token(token)
        with open(COOKIE_FILE, "w", encoding="utf-8") as file:
            file.write(cookie_string)

        await send_telegram_message("✅ *Token and cookies were successfully retrieved and saved.*")

        return token, cookie_string


async def get_device_data(token: str, cookie_string: str):
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "*/*",
        "User-Agent": "Mozilla/5.0",
        "Host": "refreshezprintsubscription.brother-usa.com",
        "Cookie": cookie_string
    }

    response = requests.get(DEVICE_URL, headers=headers)

    if response.status_code == 401:
        token, cookie_string = await browser_login_and_get_token_and_cookies()
        headers["Authorization"] = f"Bearer {token}"
        headers["Cookie"] = cookie_string
        response = requests.get(DEVICE_URL, headers=headers)

    response.raise_for_status()
    return response.json()


async def build_status_message() -> str:
    token = load_token()

    try:
        with open(COOKIE_FILE, "r", encoding="utf-8") as file:
            cookie_string = file.read().strip()
    except FileNotFoundError:
        cookie_string = ""

    if not token or not cookie_string:
        token, cookie_string = await browser_login_and_get_token_and_cookies()

    data = await get_device_data(token, cookie_string)
    device = data["deviceGroupViewModels"][0]["devices"][0]
    usage = device["service"]["currentUsage"]
    plan = device["service"]["currentPlan"]

    plan_limit = int(plan["planPages"])
    printed_total = int(usage["printedTotalPages"])
    printed_plan = int(usage["printedPlanPages"])
    printed_rollover = int(usage["printedRolloverPages"])
    given_rollover = int(usage["givenRolloverPages"])
    remaining_pages = plan_limit + given_rollover - printed_total

    alert_text = ""
    alerts = device["service"].get("subscriptionAlert", [])
    if alerts:
        alert_text = f"\n\n⚠️ {alerts[0]['alertDetail']['description']}"

    return (
        f"📠 *Printer:* {device['model']} ({device['serialNumber']})\n"
        f"📅 *Period:* {usage['usageCycleStartDate']} → {usage['usageCycleEndDate']}\n\n"
        f"✅ *Plan limit:* {plan_limit} pages\n"
        f"🔁 *Rollover:* {given_rollover} pages\n"
        f"🖨️ *Printed:* {printed_total} pages\n"
        f" └ From plan: {printed_plan}\n"
        f" └ From rollover: {printed_rollover}\n"
        f"📄 *Remaining:* {remaining_pages} pages"
        + alert_text
    )


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id != AUTHORIZED_USER_ID:
        await update.message.reply_text("⛔ Access denied.")
        return

    await update.message.reply_text("⏳ Collecting data...")

    try:
        message = await build_status_message()
        await update.message.reply_text(message, parse_mode="Markdown")
    except Exception as error:
        await update.message.reply_text(f"❌ Error: {error}")


def validate_env() -> None:
    required_vars = {
        "BROTHER_EMAIL": EMAIL,
        "BROTHER_PASSWORD": PASSWORD,
        "TELEGRAM_BOT_TOKEN": BOT_TOKEN,
        "AUTHORIZED_USER_ID": AUTHORIZED_USER_ID,
    }

    missing = [key for key, value in required_vars.items() if not value]
    if missing:
        raise RuntimeError(
            "Missing required environment variables: " + ", ".join(missing)
        )


if __name__ == "__main__":
    validate_env()

    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("status", status))

    print("Bot is running. Send /status")
    app.run_polling()
