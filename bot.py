import asyncio
import os
import io
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from aiogram.types import FSInputFile

# ---------------- CONFIG ----------------
BOT_TOKEN = "8539647721:AAEmfwcf8TCboMPK7gT1SQ-zO0VgZdlBHUE"  # Replace with your BotFather token
SERVICE_ACCOUNT_FILE = "credentials.json"  # Your service account JSON
MAIN_FOLDER_ID = "1JmQDiKZj3QYsivTHoZwJ7mFOAFCXfwAz"

SCOPES = ['https://www.googleapis.com/auth/drive.readonly']

# --------------- GOOGLE DRIVE API ---------------
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
    """Download a file from Google Drive to local temporary file"""
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
            await callback.answer()
            return
        
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[])
        for item in items:
            cb_data = f"{'folder' if item['mimeType'].endswith('folder') else 'file'}:{item['id']}:{item['name']}"
            keyboard.inline_keyboard.append(
                [types.InlineKeyboardButton(text=item['name'], callback_data=cb_data)]
            )
        await callback.message.edit_text(f"Contents of {name}:", reply_markup=keyboard)
    
    else:
        # Get file metadata to check size
        file_meta = service.files().get(fileId=file_id, fields="size,webViewLink").execute()
        file_size = int(file_meta.get("size", 0))  # size in bytes
        file_link = file_meta.get("webViewLink")   # Google Drive link
        
        if file_size <= 50 * 1024 * 1024:  # Telegram limit
            temp_file = download_file(file_id, name)
            await callback.message.answer_document(FSInputFile(temp_file))
            os.remove(temp_file)
        else:
            await callback.message.answer(f"File is too large to send via Telegram.\nDownload it here:\n{file_link}")
    
    await callback.answer()

# ---------------- RUN BOT ----------------
async def main():
    print("Bot is running!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
