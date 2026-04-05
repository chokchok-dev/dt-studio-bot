import csv
import io
import json
import requests
import threading
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ===== CONFIG =====
TOKEN = "7820622392:AAGUuofuHiRT36gCxvdb9o-NQWnWlxGZhs4"

TEAM_MEMBERS = ["Thanh Trúc", "Nhất Huy", "Phương Linh"]

CHAT_IDS_FILE = "chat_ids.json"
NOTIFY_FILE = "notify.json"

SHEET_ID = "1bY2q3VAY7f3_QoZW3sX5XvrXbGTx8xFF02EYqiPT6h8"
GID = "1553258751"

CSV_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid={GID}"

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")


# ===== FILE =====
def load_file(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}


def save_file(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)


def get_name(chat_id):
    data = load_file(CHAT_IDS_FILE)
    for name, cid in data.items():
        if str(cid) == str(chat_id):
            return name
    return None


# ===== KEYBOARD =====
def keyboard_register():
    return ReplyKeyboardMarkup(
        [["Thanh Trúc"], ["Nhất Huy", "Phương Linh"]],
        resize_keyboard=True,
        one_time_keyboard=True
    )


def keyboard_main():
    return ReplyKeyboardMarkup(
        [
            ["📋 Xem việc hôm nay"],
            ["🔄 Chọn lại tên"],
            ["⏰ Bật thông báo 7:30", "🔕 Tắt thông báo"]
        ],
        resize_keyboard=True
    )


# ===== READ SHEET =====
def get_tasks():
    res = requests.get(CSV_URL)
    text = res.content.decode("utf-8-sig")

    reader = list(csv.reader(io.StringIO(text)))
    headers = reader[1]
    rows = reader[2:]

    today = datetime.now(VN_TZ).strftime("%Y-%m-%d")

    result = {}
    current_date = ""

    for r in rows:
        r += [""] * (len(headers) - len(r))
        row = dict(zip(headers, r))

        if row["Ngày"]:
            current_date = row["Ngày"]

        if not row["TASK"]:
            continue

        users = [x.strip() for x in row["Phụ Trách"].split(",") if x.strip()]

        for u in users:
            if u not in result:
                result[u] = []

            result[u].append({
                "task": row["TASK"],
                "phan_loai": row["PHÂN LOẠI"],
                "dang": row["Dạng"],
                "nen_tang": row["Nền tảng"],
                "trang_thai": row["Trạng thái"],
                "lam_cung": ", ".join([x for x in users if x != u])
            })

    return result


# ===== FORMAT =====
def format_msg(name, tasks):
    text = f"☀️ Chào buổi sáng {name}!\n\n"

    if not tasks:
        return text + "Hôm nay bạn chưa có task nào."

    text += f"Bạn có {len(tasks)} task:\n\n"

    for i, t in enumerate(tasks, 1):
        text += f"{i}. {t['task']}\n"

        if t["phan_loai"]:
            text += f"   ├ Phân loại: {t['phan_loai']}\n"
        if t["dang"]:
            text += f"   ├ Dạng: {t['dang']}\n"
        if t["nen_tang"]:
            text += f"   ├ Nền tảng: {t['nen_tang']}\n"
        if t["lam_cung"]:
            text += f"   ├ Làm cùng: {t['lam_cung']}\n"

        text += f"   └ Trạng thái: {t['trang_thai']}\n\n"

    text += f"⚠️ Nhắc nhở: Yêu cầu {name} làm việc đúng tiến độ và cập nhật trạng thái nhé 😌"

    return text


# ===== SEND =====
async def send_today_for(context, name, chat_id):
    tasks = get_tasks().get(name, [])
    msg = format_msg(name, tasks)
    await context.bot.send_message(chat_id=chat_id, text=msg)


# ===== COMMAND =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    name = get_name(chat_id)

    if name:
        await update.message.reply_text(
            f"Chào bạn {name} ☀️",
            reply_markup=keyboard_main()
        )
        return

    await update.message.reply_text(
        "Bạn là ai trong team?",
        reply_markup=keyboard_register()
    )


async def save_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text.strip()

    if name not in TEAM_MEMBERS:
        return

    chat_id = str(update.effective_chat.id)

    data = load_file(CHAT_IDS_FILE)
    data[name] = chat_id
    save_file(CHAT_IDS_FILE, data)

    await update.message.reply_text("Đã lưu thành công ✅", reply_markup=ReplyKeyboardRemove())

    await update.message.reply_text(
        f"Chào {name} ☀️",
        reply_markup=keyboard_main()
    )

    await send_today_for(context, name, chat_id)


async def view_today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    name = get_name(chat_id)

    if not name:
        await update.message.reply_text("Chọn tên trước nha", reply_markup=keyboard_register())
        return

    await send_today_for(context, name, chat_id)


async def enable_notify(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    name = get_name(chat_id)

    notify = load_file(NOTIFY_FILE)
    notify[name] = True
    save_file(NOTIFY_FILE, notify)

    await update.message.reply_text("Đã bật 7:30 sáng ✅")


async def disable_notify(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    name = get_name(chat_id)

    notify = load_file(NOTIFY_FILE)
    notify[name] = False
    save_file(NOTIFY_FILE, notify)

    await update.message.reply_text("Đã tắt ❌")


# ===== AUTO 7:30 =====
def auto_loop(app):
    while True:
        now = datetime.now(VN_TZ)

        if now.hour == 7 and now.minute == 30:
            notify = load_file(NOTIFY_FILE)
            chat_ids = load_file(CHAT_IDS_FILE)

            for name, enabled in notify.items():
                if enabled:
                    chat_id = chat_ids.get(name)
                    if chat_id:
                        import asyncio
                        asyncio.run_coroutine_threadsafe(
                            send_today_for(app.bot_data["ctx"], name, chat_id),
                            app.bot_data["loop"]
                        )

            time.sleep(60)

        time.sleep(10)


async def post_init(app):
    import asyncio
    app.bot_data["loop"] = asyncio.get_running_loop()
    app.bot_data["ctx"] = type("ctx", (), {"bot": app.bot})()


# ===== MAIN =====
def main():
    app = ApplicationBuilder().token(TOKEN).post_init(post_init).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("sendtoday", view_today))
    app.add_handler(CommandHandler("sendeveryday", enable_notify))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, save_name))

    app.add_handler(MessageHandler(filters.Regex("📋"), view_today))
    app.add_handler(MessageHandler(filters.Regex("⏰"), enable_notify))
    app.add_handler(MessageHandler(filters.Regex("🔕"), disable_notify))

    print("Bot đang chạy...")

    t = threading.Thread(target=auto_loop, args=(app,), daemon=True)
    t.start()

    app.run_polling()


if __name__ == "__main__":
    main()
