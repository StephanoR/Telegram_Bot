import os
import io
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.types import FSInputFile
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from aiohttp import web

# ---------------- CONFIG ----------------
BOT_TOKEN = os.getenv("BOT_TOKEN")
MAIN_FOLDER_ID = os.getenv("MAIN_FOLDER_ID")
SERVICE_ACCOUNT_FILE = "credentials.json"

SCOPES = ['https://www.googleapis.com/auth/drive.readonly']

if not BOT_TOKEN:
    raise Exception("BOT_TOKEN is missing")
if not MAIN_FOLDER_ID:
    raise Exception("MAIN_FOLDER_ID is missing")

# ---------------- GOOGLE DRIVE API ----------------
credentials = service_account.Credentials.from_service_account_file(
    SERVICE_ACCOUNT_FILE, scopes=SCOPES)
service = build('drive', 'v3', credentials=credentials)

def list_folder(folder_id):
    query = f"'{folder_id}' in parents and trashed=false"
    results = service.files().list(
        q=query,
        fields="files(id, name, mimeType)"
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

# ---------------- TELEGRAM BOT ----------------
bot = Bot(BOT_TOKEN)
dp = Dispatcher()

@dp.message(types.Message)
async def start(message: types.Message):
    if message.text != "/start":
        return
    
    items = list_folder(MAIN_FOLDER_ID)
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[])

    for item in items:
        kind = "folder" if item["mimeType"].endswith("folder") else "file"
        cb_data = f"{kind}:{item['id']}:{item['name']}"
        keyboard.inline_keyboard.append(
            [types.InlineKeyboardButton(text=item['name'], callback_data=cb_data)]
        )

    await message.answer("Select a folder or file:", reply_markup=keyboard)

@dp.callback_query()
async def handle_callbacks(callback: types.CallbackQuery):
    kind, file_id, name = callback.data.split(":", 2)

    if kind == "folder":
        items = list_folder(file_id)
        if not items:
            return await callback.message.edit_text(f"{name} is empty.")

        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[])
        for item in items:
            k = "folder" if item["mimeType"].endswith("folder") else "file"
            cb_data = f"{k}:{item['id']}:{item['name']}"
            keyboard.inline_keyboard.append(
                [types.InlineKeyboardButton(text=item['name'], callback_data=cb_data)]
            )

        await callback.message.edit_text(f"Contents of {name}:", reply_markup=keyboard)

    else:
        file_meta = service.files().get(fileId=file_id, fields="size,webViewLink").execute()
        size = int(file_meta.get("size", 0))

        if size <= 50 * 1024 * 1024:
            temp_file = download_file(file_id, name)
            await callback.message.answer_document(FSInputFile(temp_file))
            os.remove(temp_file)
        else:
            await callback.message.answer(f"Too large. Download:\n{file_meta['webViewLink']}")

# ---------------- WEBHOOK SERVER ----------------
async def telegram_webhook(request):
    data = await request.json()
    await dp.feed_webhook_update(bot, data)
    return web.Response(text="ok")

async def start_app():
    app = web.Application()
    app.router.add_post(f"/webhook", telegram_webhook)
    app.router.add_get("/", lambda _: web.Response(text="Bot is running"))
    return app

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    web.run_app(start_app(), host="0.0.0.0", port=port)
