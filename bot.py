import os
import io
import asyncio
from aiogram import Bot, Dispatcher
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from aiogram.filters import Command
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from aiohttp import web
from aiogram.types import FSInputFile

# ---------------- CONFIG ----------------
BOT_TOKEN = os.getenv("8539647721:AAEmfwcf8TCboMPK7gT1SQ-zO0VgZdlBHUE")  # Set this in Cloud Run environment variables
SERVICE_ACCOUNT_FILE = "credentials.json"  # Keep this file in your repo
MAIN_FOLDER_ID = os.getenv("1JmQDiKZj3QYsivTHoZwJ7mFOAFCXfwAz")  # e.g., your Google Drive folder ID
SCOPES = ['https://www.googleapis.com/auth/drive.readonly']

# ---------------- GOOGLE DRIVE API ----------------
credentials = service_account.Credentials.from_service_account_file(
    SERVICE_ACCOUNT_FILE, scopes=SCOPES)
service = build('drive', 'v3', credentials=credentials)

def list_folder(folder_id):
    """Return list of files/folders inside a folder"""
    query = f"'{folder_id}' in parents and trashed=false"
    results = service.files().list(
        q=query,
        fields="files(id, name, mimeType)"
    ).execute()
    return results.get('files', [])

def download_file(file_id, file_name):
    """Download a file from Google Drive to a local temporary file"""
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

@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    items = list_folder(MAIN_FOLDER_ID)
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[])
    
    for item in items:
        cb_data = f"{'folder' if item['mimeType'].endswith('folder') else 'file'}:{item['id']}:{item['name']}"
        keyboard.inline_keyboard.append(
            [types.InlineKeyboardButton(text=item['name'], callback_data=cb_data)]
        )
    await message.answer("Select a folder or file:", reply_markup=keyboard)

@dp.callback_query()
async def handle_callbacks(callback: types.CallbackQuery):
    kind, file_id, name = callback.data.split(':', 2)
    
    if kind == 'folder':
        items = list_folder(file_id)
        if not items:
            await callback.message.edit_text(f"{name} is empty.")
            return
        
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[])
        for item in items:
            cb_data = f"{'folder' if item['mimeType'].endswith('folder') else 'file'}:{item['id']}:{item['name']}"
            keyboard.inline_keyboard.append(
                [types.InlineKeyboardButton(text=item['name'], callback_data=cb_data)]
            )
        await callback.message.edit_text(f"Contents of {name}:", reply_markup=keyboard)
    
    else:
        file_meta = service.files().get(fileId=file_id, fields="size,webViewLink").execute()
        file_size = int(file_meta.get("size", 0))
        file_link = file_meta.get("webViewLink")
        
        if file_size <= 50 * 1024 * 1024:  # Telegram limit 50MB
            temp_file = download_file(file_id, name)
            await callback.message.answer_document(FSInputFile(temp_file))
            os.remove(temp_file)
        else:
            await callback.message.answer(f"File is too large for Telegram.\nDownload it here:\n{file_link}")

# ---------------- HTTP SERVER FOR CLOUD RUN ----------------
async def handle(request):
    return web.Response(text="Bot is running!")

async def start_http_server():
    app = web.Application()
    app.router.add_get("/", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print(f"HTTP server running on port {port}")

# ---------------- MAIN ----------------
async def main():
    # Start HTTP server for Cloud Run health checks
    await start_http_server()
    # Start Telegram bot polling
    print("Bot is running!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
