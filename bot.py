import os
import io
import asyncio
from aiohttp import web
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

# ---------------- ENV VARIABLES ----------------
BOT_TOKEN = os.getenv("BOT_TOKEN")
MAIN_FOLDER_ID = os.getenv("MAIN_FOLDER_ID")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # Cloud Run URL + /webhook

if not BOT_TOKEN:
    raise Exception("❌ Missing BOT_TOKEN environment variable!")

if not MAIN_FOLDER_ID:
    raise Exception("❌ Missing MAIN_FOLDER_ID!")

if not WEBHOOK_URL:
    raise Exception("❌ Missing WEBHOOK_URL!")

# ---------------- GOOGLE DRIVE ----------------
SERVICE_ACCOUNT_FILE = "credentials.json"
SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]

credentials = service_account.Credentials.from_service_account_file(
    SERVICE_ACCOUNT_FILE, scopes=SCOPES
)
drive = build("drive", "v3", credentials=credentials)

# ---------------- BOT SETUP ----------------
bot = Bot(BOT_TOKEN)
dp = Dispatcher()


def list_folder(folder_id):
    query = f"'{folder_id}' in parents and trashed=false"
    results = drive.files().list(
        q=query,
        fields="files(id,name,mimeType)"
    ).execute()
    return results.get("files", [])


def download_file(file_id, file_name):
    request = drive.files().get_media(fileId=file_id)
    f = io.FileIO(file_name, 'wb')
    downloader = MediaIoBaseDownload(f, request)
    done = False
    while not done:
        status, done = downloader.next_chunk()
    return file_name


# ---------------- BOT HANDLERS ----------------
@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    items = list_folder(MAIN_FOLDER_ID)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[])

    for item in items:
        kind = "folder" if item["mimeType"].endswith("folder") else "file"
        keyboard.inline_keyboard.append([
            InlineKeyboardButton(
                text=item["name"],
                callback_data=f"{kind}:{item['id']}:{item['name']}"
            )
        ])

    await message.answer("📁 Select a folder or file:", reply_markup=keyboard)


@dp.callback_query()
async def callback_handler(call: types.CallbackQuery):
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
                InlineKeyboardButton(
                    text=item["name"],
                    callback_data=f"{kind2}:{item['id']}:{item['name']}"
                )
            ])

        await call.message.edit_text(f"📁 Contents of {name}:", reply_markup=keyboard)

    else:
        meta = drive.files().get(fileId=file_id, fields="size, webViewLink").execute()
        size = int(meta.get("size", 0))
        link = meta.get("webViewLink")

        if size <= 50 * 1024 * 1024:
            path = download_file(file_id, name)
            await call.message.answer_document(FSInputFile(path))
            os.remove(path)
        else:
            await call.message.answer(f"⚠️ Too large.\nDownload:\n{link}")


# ---------------- WEBHOOK SERVER (Cloud Run) ----------------
async def handle_webhook(request):
    update = await request.json()
    await dp.feed_raw_update(bot, update)
    return web.Response(text="ok")


async def health(request):
    return web.Response(text="Bot OK")


async def main():
    port = int(os.getenv("PORT", 8080))
    app = web.Application()
    app.router.add_post("/webhook", handle_webhook)
    app.router.add_get("/", health)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print(f"Server running on port {port}")

    # Now set the webhook AFTER the server is up
    await bot.delete_webhook()
    await bot.set_webhook(WEBHOOK_URL)
    print(f"Webhook set: {WEBHOOK_URL}")

    # Keep alive
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
