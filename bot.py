import os
import io
import asyncio
import logging
from aiohttp import web
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

# ---------------- LOGGING ----------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------- ENV VARIABLES ----------------
BOT_TOKEN = os.getenv("BOT_TOKEN")
MAIN_FOLDER_ID = os.getenv("MAIN_FOLDER_ID")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # Cloud Run URL + /webhook

# Check required environment variables
missing_vars = [var for var in ["BOT_TOKEN", "MAIN_FOLDER_ID", "WEBHOOK_URL"] if not os.getenv(var)]
if missing_vars:
    raise Exception(f"❌ Missing environment variables: {', '.join(missing_vars)}")

# ---------------- GOOGLE DRIVE ----------------
SERVICE_ACCOUNT_FILE = "credentials.json"
SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]

if not os.path.exists(SERVICE_ACCOUNT_FILE):
    raise FileNotFoundError(f"❌ {SERVICE_ACCOUNT_FILE} not found in container!")

credentials = service_account.Credentials.from_service_account_file(
    SERVICE_ACCOUNT_FILE, scopes=SCOPES
)
drive = build("drive", "v3", credentials=credentials)

# ---------------- BOT SETUP ----------------
bot = Bot(BOT_TOKEN)
dp = Dispatcher()

# ---------------- GOOGLE DRIVE FUNCTIONS ----------------
def list_folder(folder_id):
    try:
        query = f"'{folder_id}' in parents and trashed=false"
        results = drive.files().list(q=query, fields="files(id,name,mimeType)").execute()
        return results.get("files", [])
    except Exception as e:
        logger.exception("Failed to list folder")
        return []

def download_file(file_id, file_name):
    try:
        request = drive.files().get_media(fileId=file_id)
        with io.FileIO(file_name, 'wb') as f:
            downloader = MediaIoBaseDownload(f, request)
            done = False
            while not done:
                status, done = downloader.next_chunk()
        return file_name
    except Exception as e:
        logger.exception(f"Failed to download file {file_name}")
        return None

# ---------------- BOT HANDLERS ----------------
@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    try:
        items = list_folder(MAIN_FOLDER_ID)
        keyboard = InlineKeyboardMarkup(inline_keyboard=[])

        for item in items:
            kind = "folder" if item["mimeType"].endswith("folder") else "file"
            keyboard.inline_keyboard.append([
                InlineKeyboardButton(text=item["name"], callback_data=f"{kind}:{item['id']}:{item['name']}")
            ])
        await message.answer("📁 Select a folder or file:", reply_markup=keyboard)
    except Exception as e:
        logger.exception("Error in /start handler")
        await message.answer("⚠️ Something went wrong. Check logs.")

@dp.callback_query()
async def callback_handler(call: types.CallbackQuery):
    try:
        kind, file_id, name = call.data.split(":", 2)

        if kind == "folder":
            items = list_folder(file_id)
            if not items:
                await call.message.edit_text(f"{name} is empty.")
                return

            keyboard = InlineKeyboardMarkup(inline_keyboard=[])
            for item in items:
                kind2 = "folder" if item["mimeType"].endswith("folder") else "file"
                keyboard.inline_keyboard.append([
                    InlineKeyboardButton(text=item["name"], callback_data=f"{kind2}:{item['id']}:{item['name']}")
                ])
            await call.message.edit_text(f"📁 Contents of {name}:", reply_markup=keyboard)

        else:
            meta = drive.files().get(fileId=file_id, fields="size, webViewLink").execute()
            size = int(meta.get("size", 0))
            link = meta.get("webViewLink")

            if size <= 50 * 1024 * 1024:
                path = download_file(file_id, name)
                if path:
                    await call.message.answer_document(FSInputFile(path))
                    os.remove(path)
                else:
                    await call.message.answer("⚠️ Failed to download the file.")
            else:
                await call.message.answer(f"⚠️ Too large.\nDownload:\n{link}")
    except Exception as e:
        logger.exception("Error in callback handler")
        await call.message.answer("⚠️ Something went wrong. Check logs.")

# ---------------- WEBHOOK SERVER (Cloud Run) ----------------
async def handle_webhook(request):
    try:
        update = await request.json()
        await dp.feed_raw_update(bot, update)
        return web.Response(text="ok")
    except Exception as e:
        logger.exception("Error handling webhook")
        return web.Response(status=500, text="Internal Server Error")

async def health(request):
    return web.Response(text="Bot OK")

# ---------------- MAIN ----------------
async def main():
    # ---- Set webhook ----
    try:
        await bot.delete_webhook()
        await bot.set_webhook(WEBHOOK_URL)
        logger.info(f"Webhook set: {WEBHOOK_URL}")
    except Exception as e:
        logger.exception("Failed to set webhook")

    # ---- Start webhook server ----
    app = web.Application()
    app.router.add_post("/webhook", handle_webhook)
    app.router.add_get("/", health)

    port = int(os.getenv("PORT", 8080))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info(f"Webhook server running on port {port}")

    # Keep alive
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
