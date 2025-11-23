import os
import io
import asyncio
from aiohttp import web
from aiogram import Bot, Dispatcher, types
from aiogram.types import FSInputFile
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

# ==============================
# ENVIRONMENT VARIABLES
# ==============================
BOT_TOKEN = os.getenv("8539647721:AAEmfwcf8TCboMPK7gT1SQ-zO0VgZdlBHUE")
WEBHOOK_URL = os.getenv("https://telegram-bot-183501981846.europe-west1.run.app/webhook/8539647721:AAEmfwcf8TCboMPK7gT1SQ-zO0VgZdlBHUE")  # https://your-cloudrun-url/webhook/<token>
MAIN_FOLDER_ID = os.getenv("1JmQDiKZj3QYsivTHoZwJ7mFOAFCXfwAz")  # Google Drive main folder id
SERVICE_ACCOUNT_FILE = "credentials.json"

SCOPES = ['https://www.googleapis.com/auth/drive.readonly']

# ==============================
# GOOGLE DRIVE SETUP
# ==============================
credentials = service_account.Credentials.from_service_account_file(
    SERVICE_ACCOUNT_FILE, scopes=SCOPES
)
service = build('drive', 'v3', credentials=credentials)

def list_folder(folder_id):
    query = f"'{folder_id}' in parents and trashed=false"
    results = service.files().list(
        q=query,
        fields="files(id, name, mimeType, size)"
    ).execute()
    return results.get('files', [])

def download_file(file_id, file_name):
    request = service.files().get_media(fileId=file_id)
    fh = io.FileIO(file_name, 'wb')
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done:
        status, done = downloader.next_chunk()
    return file_name

# ==============================
# TELEGRAM BOT SETUP
# ==============================
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# ---------------- START COMMAND ----------------
@dp.message(types.Message, commands={"start"})
async def start(message: types.Message):
    items = list_folder(MAIN_FOLDER_ID)
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[])

    for item in items:
        knob = "folder" if item["mimeType"].endswith("folder") else "file"
        cb_data = f"{knob}:{item['id']}:{item['name']}"
        keyboard.inline_keyboard.append([
            types.InlineKeyboardButton(text=item["name"], callback_data=cb_data)
        ])

    await message.answer("Select a folder:", reply_markup=keyboard)

# ---------------- CALLBACK HANDLER ----------------
@dp.callback_query()
async def handle_callback(callback: types.CallbackQuery):
    kind, file_id, name = callback.data.split(":", 2)

    if kind == "folder":
        items = list_folder(file_id)
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[])

        for item in items:
            knob = "folder" if item["mimeType"].endswith("folder") else "file"
            cb_data = f"{knob}:{item['id']}:{item['name']}"
            keyboard.inline_keyboard.append([
                types.InlineKeyboardButton(text=item["name"], callback_data=cb_data)
            ])

        await callback.message.edit_text(f"Contents of {name}:", reply_markup=keyboard)

    else:
        file_meta = service.files().get(fileId=file_id, fields="size,webViewLink").execute()
        file_size = int(file_meta.get("size", 0))
        file_link = file_meta.get("webViewLink")

        if file_size <= 50 * 1024 * 1024:  # <=50MB
            temp = download_file(file_id, name)
            await callback.message.answer_document(FSInputFile(temp))
            os.remove(temp)
        else:
            await callback.message.answer(
                f"📁 File is too large to send on Telegram.\nDownload here:\n{file_link}"
            )

# ==============================
# AIOHTTP SERVER FOR WEBHOOKS
# ==============================
async def webhook_handler(request):
    body = await request.json()
    update = types.Update.to_object(body)
    await dp.feed_update(bot, update)
    return web.Response(text="OK")

async def on_startup(app):
    await bot.set_webhook(WEBHOOK_URL)

async def on_shutdown(app):
    await bot.delete_webhook()

def create_app():
    app = web.Application()
    app.router.add_post(f"/webhook/{BOT_TOKEN}", webhook_handler)
    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)
    return app

if __name__ == "__main__":
    PORT = int(os.environ.get("PORT", 8080))
    web.run_app(create_app(), port=PORT)
