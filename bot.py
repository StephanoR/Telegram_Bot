import os
import io
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from aiogram.filters import Command
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from aiohttp import web

# ---------------- CONFIG ----------------
BOT_TOKEN = os.getenv("BOT_TOKEN")  # Cloud Run env var
MAIN_FOLDER_ID = os.getenv("MAIN_FOLDER_ID")  # Cloud Run env var
SERVICE_ACCOUNT_FILE = "credentials.json"

if not BOT_TOKEN:
    raise Exception("❌ BOT_TOKEN environment variable is missing!")

if not MAIN_FOLDER_ID:
    raise Exception("❌ MAIN_FOLDER_ID environment variable is missing!")

SCOPES = ['https://www.googleapis.com/auth/drive.readonly']

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


@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    items = list_folder(MAIN_FOLDER_ID)

    keyboard = InlineKeyboardMarkup(inline_keyboard=[])

    for item in items:
        cb_data = f"{'folder' if item['mimeType'].endswith('folder') else 'file'}:{item['id']}:{item['name']}"
        keyboard.inline_keyboard.append(
            [InlineKeyboardButton(text=item['name'], callback_data=cb_data)]
        )

    await message.answer("📁 Select a folder or file:", reply_markup=keyboard)


@dp.callback_query()
async def handle_callbacks(callback: types.CallbackQuery):
    kind, file_id, name = callback.data.split(':', 2)

    if kind == "folder":
        items = list_folder(file_id)

        if not items:
            await callback.message.edit_text(f"{name} is empty.")
            return

        keyboard = InlineKeyboardMarkup(inline_keyboard=[])

        for item in items:
            cb_data = f"{'folder' if item['mimeType'].endswith('folder') else 'file'}:{item['id']}:{item['name']}"
            keyboard.inline_keyboard.append(
                [InlineKeyboardButton(text=item['name'], callback_data=cb_data)]
            )

        await callback.message.edit_text(f"📁 Contents of {name}:", reply_markup=keyboard)

    else:
        # file
        file_meta = service.files().get(fileId=file_id, fields="size,webViewLink").execute()
        size = int(file_meta.get("size", 0))
        link = file_meta.get("webViewLink")

        if size <= 50 * 1024 * 1024:
            temp = download_file(file_id, name)
            await callback.message.answer_document(FSInputFile(temp))
            os.remove(temp)
        else:
            await callback.message.answer(f"⚠️ File too large for Telegram.\nDownload:\n{link}")


# ---------------- HTTP SERVER FOR CLOUD RUN ----------------
async def handle(request):
    return web.Response(text="Bot OK")

async def start_server():
    app = web.Application()
    app.router.add_get("/", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print(f"HTTP health server running on port {port}")


# ---------------- MAIN ----------------
async def main():
    await start_server()
    print("Starting Telegram bot polling...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
