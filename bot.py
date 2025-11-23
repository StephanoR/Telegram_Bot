import os
import io
import asyncio
from aiohttp import web
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, FSInputFile
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

# ---------------- CONFIG ----------------
BOT_TOKEN = os.getenv("8539647721:AAEmfwcf8TCboMPK7gT1SQ-zO0VgZdlBHUE")  # Set in Cloud Run environment variables
SERVICE_ACCOUNT_FILE = "credentials.json"  # Include in container
MAIN_FOLDER_ID = "1JmQDiKZj3QYsivTHoZwJ7mFOAFCXfwAz"
SCOPES = ['https://www.googleapis.com/auth/drive.readonly']
PORT = int(os.getenv("PORT", 8080))
WEBHOOK_URL = os.getenv("https://telegram-bot-183501981846.europe-west1.run.app")  # e.g., https://<your-service>.run.app

# --------------- GOOGLE DRIVE API ---------------
credentials = service_account.Credentials.from_service_account_file(
    SERVICE_ACCOUNT_FILE, scopes=SCOPES
)
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

@dp.message(types.filters.Command("start"))
async def start_cmd(message: types.Message):
    items = list_folder(MAIN_FOLDER_ID)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[])
    for item in items:
        cb_data = f"{'folder' if item['mimeType'].endswith('folder') else 'file'}:{item['id']}:{item['name']}"
        keyboard.inline_keyboard.append([InlineKeyboardButton(text=item['name'], callback_data=cb_data)])
    await message.answer("Select a folder or file:", reply_markup=keyboard)

@dp.callback_query()
async def handle_callbacks(callback: types.CallbackQuery):
    kind, file_id, name = callback.data.split(':', 2)
    
    if kind == 'folder':
        items = list_folder(file_id)
        if not items:
            await callback.message.edit_text(f"{name} is empty.")
            return
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[])
        for item in items:
            cb_data = f"{'folder' if item['mimeType'].endswith('folder') else 'file'}:{item['id']}:{item['name']}"
            keyboard.inline_keyboard.append([InlineKeyboardButton(text=item['name'], callback_data=cb_data)])
        await callback.message.edit_text(f"Contents of {name}:", reply_markup=keyboard)
    
    else:
        # Get file metadata
        file_meta = service.files().get(fileId=file_id, fields="size, webViewLink").execute()
        file_size = int(file_meta.get("size", 0))
        file_link = file_meta.get("webViewLink")
        
        if file_size <= 50 * 1024 * 1024:  # Telegram file limit
            temp_file = download_file(file_id, name)
            await callback.message.answer_document(FSInputFile(temp_file))
            os.remove(temp_file)
        else:
            await callback.message.answer(f"File too large for Telegram.\nDownload here: {file_link}")

# ---------------- WEBHOOK SERVER ----------------
async def on_startup(app):
    await bot.set_webhook(f"{WEBHOOK_URL}/webhook/{BOT_TOKEN}")

async def on_shutdown(app):
    await bot.delete_webhook()
    await bot.session.close()

app = web.Application()
app.router.add_post(f"/webhook/{BOT_TOKEN}", dp.start_webhook)
app.on_startup.append(on_startup)
app.on_cleanup.append(on_shutdown)

if __name__ == "__main__":
    web.run_app(app, port=PORT)
