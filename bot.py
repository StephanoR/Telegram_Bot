import asyncio
import os
import io
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from aiogram.types import FSInputFile

from fastapi import FastAPI
import uvicorn

# ----- CONFIG -----
BOT_TOKEN = os.getenv("8539647721:AAEmfwcf8TCboMPK7gT1SQ-zO0VgZdlBHUE")
SERVICE_ACCOUNT_FILE = "credentials.json"
MAIN_FOLDER_ID = "1JmQDiKZj3QYsivTHoZwJ7mFOAFCXfwAz"
SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]

# ----- GOOGLE DRIVE -----
credentials = service_account.Credentials.from_service_account_file(
    SERVICE_ACCOUNT_FILE, scopes=SCOPES
)
service = build("drive", "v3", credentials=credentials)

def list_folder(folder_id):
    query = f"'{folder_id}' in parents and trashed=false"
    results = service.files().list(
        q=query,
        fields="files(id, name, mimeType)"
    ).execute()
    return results.get("files", [])

def download_file(file_id, name):
    request = service.files().get_media(fileId=file_id)
    fh = io.FileIO(name, 'wb')
    downloader = MediaIoBaseDownload(fh, request)

    done = False
    while not done:
        _, done = downloader.next_chunk()
    return name

# ----- TELEGRAM BOT -----
bot = Bot(BOT_TOKEN)
dp = Dispatcher()

@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    items = list_folder(MAIN_FOLDER_ID)

    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[])

    for item in items:
        cb = f"{'folder' if item['mimeType'].endswith('folder') else 'file'}:{item['id']}:{item['name']}"
        keyboard.inline_keyboard.append(
            [types.InlineKeyboardButton(text=item["name"], callback_data=cb)]
        )

    await message.answer("Select a folder or file:", reply_markup=keyboard)

@dp.callback_query()
async def handle_cb(callback: types.CallbackQuery):
    kind, file_id, name = callback.data.split(":", 2)

    if kind == "folder":
        items = list_folder(file_id)
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[])

        for item in items:
            cb = f"{'folder' if item['mimeType'].endswith('folder') else 'file'}:{item['id']}:{item['name']}"
            keyboard.inline_keyboard.append(
                [types.InlineKeyboardButton(text=item["name"], callback_data=cb)]
            )

        await callback.message.edit_text(f"Contents of {name}:", reply_markup=keyboard)

    else:
        info = service.files().get(fileId=file_id, fields="size,webViewLink").execute()
        size = int(info.get("size", 0))

        if size <= 50 * 1024 * 1024:
            temp = download_file(file_id, name)
            await callback.message.answer_document(FSInputFile(temp))
            os.remove(temp)
        else:
            await callback.message.answer(
                f"File too large for Telegram. Download here:\n{info['webViewLink']}"
            )

# ----- FASTAPI SERVER FOR CLOUD RUN -----
app = FastAPI()

@app.get("/")
def home():
    return {"status": "Bot is running"}

async def start_bot():
    await dp.start_polling(bot)

# Run both API + bot together
def start():
    loop = asyncio.get_event_loop()
    loop.create_task(start_bot())

    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8080)))

if __name__ == "__main__":
    start()
