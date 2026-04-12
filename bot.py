import os
import io
import csv
import json
import time
import asyncio
import threading
import requests
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

# =========================
# CONFIG
# =========================
TOKEN = os.getenv("TOKEN")

TEAM_MEMBERS = ["Thanh Trúc", "Nhất Huy", "Phương Linh"]

CHAT_IDS_FILE = "chat_ids.json"
NOTIFY_FILE = "notify.json"

SHEET_ID = "1bY2q3VAY7f3_QoZW3sX5XvrXbGTx8xFF02EYqiPT6h8"
GID = "1553258751"

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")


# =========================
# FILE HELPERS
# =========================
def load_file(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_file(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_name_by_chat_id(chat_id: str):
    data = load_file(CHAT_IDS_FILE)
    for name, cid in data.items():
        if str(cid) == str(chat_id):
            return name
    return None


# =========================
# KEYBOARDS
# =========================
def keyboard_register():
    return ReplyKeyboardMarkup(
        [["Thanh Trúc"], ["Nhất Huy", "Phương Linh"]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def keyboard_main():
    return ReplyKeyboardMarkup(
        [
            ["📋 Xem việc hôm nay"],
            ["🔄 Chọn lại tên"],
            ["⏰ Bật thông báo 7:30", "🔕 Tắt thông báo"],
        ],
        resize_keyboard=True,
    )


# =========================
# SHEET HELPERS
# =========================
def get_csv_url():
    # thêm timestamp để tránh cache
    return f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid={GID}&t={int(time.time())}"


def split_multi_value(value):
    if not value:
        return []
    txt = str(value).replace("\n", ",")
    return [x.strip() for x in txt.split(",") if x.strip()]


def normalize_date_text(date_text):
    """
    Nhận các kiểu:
    - 'Thứ 2, 7/4/26'
    - 'CN, 6/4/26'
    - '7/4/26'
    Trả về: YYYY-MM-DD
    """
    if not date_text:
        return ""

    txt = str(date_text).strip()

    if "," in txt:
        txt = txt.split(",", 1)[1].strip()

    txt = txt.replace("-", "/").replace(".", "/")
    parts = txt.split("/")

    if len(parts) != 3:
        return ""

    d, m, y = [p.strip() for p in parts]

    if len(y) == 2:
        y = "20" + y

    try:
        dt = datetime(int(y), int(m), int(d))
        return dt.strftime("%Y-%m-%d")
    except Exception:
        return ""


def today_key():
    return datetime.now(VN_TZ).strftime("%Y-%m-%d")


def build_tasks_for_today():
    """
    Trả về:
    {
      "Thanh Trúc": [ {...}, {...} ],
      "Nhất Huy": [ {...} ]
    }
    Chỉ lấy task của ngày hôm nay.
    """
    res = requests.get(get_csv_url(), timeout=30)
    res.raise_for_status()

    text = res.content.decode("utf-8-sig")
    reader = list(csv.reader(io.StringIO(text)))

    if len(reader) < 3:
        return {}

    headers = [h.strip() for h in reader[1]]
    rows = reader[2:]

    result = {}
    today = today_key()

    current_date_raw = ""
    current_date_norm = ""

    for r in rows:
        r += [""] * (len(headers) - len(r))
        row = dict(zip(headers, r))

        ngay = str(row.get("Ngày", "")).strip()

        # nếu có ngày thì cập nhật ngày hiện tại
        if ngay:
            current_date_raw = ngay
            current_date_norm = normalize_date_text(ngay)

        # nếu dòng không có ngày thì lấy ngày của dòng trước (do merge ô)
        ngay_hien_tai = current_date_raw
        ngay_norm_hien_tai = current_date_norm

        # chỉ lấy đúng task của hôm nay
        if ngay_norm_hien_tai != today:
            continue

        task = str(row.get("TASK", "")).strip()
        if not task:
            continue

        users = split_multi_value(row.get("Phụ Trách", ""))

        for u in users:
            if u not in result:
                result[u] = []

            lam_cung = ", ".join([x for x in users if x != u])

            result[u].append(
                {
                    "ngay_raw": ngay_hien_tai,
                    "task": task,
                    "phan_loai": str(row.get("PHÂN LOẠI", "")).strip(),
                    "dang": str(row.get("Dạng", "")).strip(),
                    "nen_tang": str(row.get("Nền tảng", "")).strip(),
                    "trang_thai": str(row.get("Trạng thái", "")).strip(),
                    "lam_cung": lam_cung,
                }
            )

    return result


# =========================
# FORMAT MESSAGE
# =========================
def format_msg(name, tasks):
    text = f"☀️ Chào buổi sáng {name}!\n\n"

    if not tasks:
        return text + "Hôm nay bạn chưa có task nào."

    ngay = tasks[0].get("ngay_raw", "")
    if ngay:
        text += f"Hôm nay là {ngay}\n"
    text += f"Bạn có {len(tasks)} task:\n\n"

    for i, t in enumerate(tasks, 1):
        text += f"{i}. {t['task']}\n"

        if t["phan_loai"]:
            text += f"├ Phân loại: {t['phan_loai']}\n"
        if t["dang"]:
            text += f"├ Dạng: {t['dang']}\n"
        if t["nen_tang"]:
            text += f"├ Nền tảng: {t['nen_tang']}\n"
        if t["lam_cung"]:
            text += f"├ Làm cùng: {t['lam_cung']}\n"
        if t["trang_thai"]:
            text += f"└ Trạng thái: {t['trang_thai']}\n"

        text += "\n"

    text += f"⚠️ Nhắc nhở: Yêu cầu {name} làm việc đúng tiến độ và cập nhật trạng thái vào sheet, nếu quên cập nhật thì sẽ bị rắn cắn vào đích🐍🐍"
    return text.strip()


# =========================
# SEND HELPERS
# =========================
async def send_today_for_name(bot, name, chat_id):
    tasks_by_user = build_tasks_for_today()
    tasks = tasks_by_user.get(name, [])
    msg = format_msg(name, tasks)
    await bot.send_message(chat_id=chat_id, text=msg)

    report = build_report_text(name, tasks)
    await bot.send_message(chat_id=chat_id, text=report)

def build_report_text(name, tasks):
    from datetime import datetime
    today = datetime.now().strftime("%d/%m")

    text = f"{name} Báo cáo {today}:\n"

    for t in tasks:
        text += f"- {t.get('phan_loai', '')}\n"

    return text
# =========================
# COMMANDS
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    name = get_name_by_chat_id(chat_id)

    if name:
        await update.message.reply_text(
            f"Chào bạn {name} ☀️",
            reply_markup=keyboard_main(),
        )
        return

    await update.message.reply_text(
        "Bạn là ai trong team?",
        reply_markup=keyboard_register(),
    )


async def save_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    name = update.message.text.strip()
    if name not in TEAM_MEMBERS:
        return

    chat_id = str(update.effective_chat.id)
    data = load_file(CHAT_IDS_FILE)

    # xóa tên cũ đang trỏ cùng chat_id
    to_delete = [n for n, cid in data.items() if str(cid) == chat_id]
    for n in to_delete:
        del data[n]

    # lưu tên mới
    data[name] = chat_id
    save_file(CHAT_IDS_FILE, data)

    await update.message.reply_text(
        f"Đã lưu {name} thành công ✅",
        reply_markup=ReplyKeyboardRemove(),
    )

    await update.message.reply_text(
        f"Chào bạn {name} ☀️",
        reply_markup=keyboard_main(),
    )

    await send_today_for_name(context.bot, name, chat_id)


async def view_today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    name = get_name_by_chat_id(chat_id)

    if not name:
        await update.message.reply_text(
            "Bạn chưa chọn tên nha. Bấm /start để chọn tên trước nhé.",
            reply_markup=keyboard_register(),
        )
        return

    await send_today_for_name(context.bot, name, chat_id)


async def choose_again(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Oke, bạn chọn lại tên của mình nha 👇",
        reply_markup=keyboard_register(),
    )


async def enable_notify(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    name = get_name_by_chat_id(chat_id)

    if not name:
        await update.message.reply_text(
            "Bạn chưa chọn tên nha. Bấm /start để chọn tên trước nhé.",
            reply_markup=keyboard_register(),
        )
        return

    notify = load_file(NOTIFY_FILE)
    notify[name] = {
        "enabled": True,
        "last_sent": notify.get(name, {}).get("last_sent", "")
    }
    save_file(NOTIFY_FILE, notify)

    await update.message.reply_text(
        "Đã bật thông báo công việc mỗi ngày lúc 7:30 sáng ✅",
        reply_markup=keyboard_main(),
    )


async def disable_notify(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    name = get_name_by_chat_id(chat_id)

    if not name:
        await update.message.reply_text(
            "Bạn chưa chọn tên nha. Bấm /start để chọn tên trước nhé.",
            reply_markup=keyboard_register(),
        )
        return

    notify = load_file(NOTIFY_FILE)
    notify[name] = {
        "enabled": False,
        "last_sent": notify.get(name, {}).get("last_sent", "")
    }
    save_file(NOTIFY_FILE, notify)

    await update.message.reply_text(
        "Đã tắt thông báo 7:30 sáng ❌",
        reply_markup=keyboard_main(),
    )


async def sendtoday_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await view_today(update, context)


async def sendeveryday_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await enable_notify(update, context)

async def pingteam_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_ids = load_file(CHAT_IDS_FILE)

    text = (
        "📣 Có cập nhật công việc mới trong sheet nha.\n"
        "Mọi người vào bot bấm /sendtoday hoặc nút 📋 Xem việc hôm nay để xem task mới nhất."
    )

    for name, chat_id in chat_ids.items():
        try:
            await context.bot.send_message(chat_id=chat_id, text=text)
        except Exception as e:
            print(f"Lỗi ping {name}: {e}")

    if update.message:
        await update.message.reply_text("Đã ping toàn bộ team ✅")

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Dùng /start để bắt đầu, /sendtoday để xem việc hôm nay, /sendeveryday để bật nhắc 7:30.",
        reply_markup=keyboard_main(),
    )


# =========================
# AUTO 7:30
# =========================
def auto_loop(app):
    while True:
        try:
            now = datetime.now(VN_TZ)
            today = now.strftime("%Y-%m-%d")

            if now.hour == 7 and now.minute == 30:
                notify = load_file(NOTIFY_FILE)
                chat_ids = load_file(CHAT_IDS_FILE)

                for name, cfg in notify.items():
                    if not cfg.get("enabled", False):
                        continue

                    if cfg.get("last_sent") == today:
                        continue

                    chat_id = chat_ids.get(name)
                    if not chat_id:
                        continue

                    future = asyncio.run_coroutine_threadsafe(
                        send_today_for_name(app.bot, name, chat_id),
                        app.bot_data["loop"],
                    )
                    future.result(timeout=60)

                    notify[name]["last_sent"] = today
                    save_file(NOTIFY_FILE, notify)

                time.sleep(60)

            time.sleep(10)

        except Exception as e:
            print("Auto loop lỗi:", e)
            time.sleep(10)


async def post_init(app):
    app.bot_data["loop"] = asyncio.get_running_loop()
    try:
        await app.bot.delete_webhook(drop_pending_updates=True)
    except Exception:
        pass


# =========================
# MAIN
# =========================
def main():
    if not TOKEN:
        raise ValueError("Thiếu TOKEN trong Railway Variables")

    app = ApplicationBuilder().token(TOKEN).post_init(post_init).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("sendtoday", sendtoday_cmd))
    app.add_handler(CommandHandler("sendeveryday", sendeveryday_cmd))
    app.add_handler(CommandHandler("pingteam", pingteam_cmd))
    app.add_handler(CommandHandler("help", help_cmd))

    app.add_handler(MessageHandler(filters.Regex("^📋 Xem việc hôm nay$"), view_today))
    app.add_handler(MessageHandler(filters.Regex("^🔄 Chọn lại tên$"), choose_again))
    app.add_handler(MessageHandler(filters.Regex("^⏰ Bật thông báo 7:30$"), enable_notify))
    app.add_handler(MessageHandler(filters.Regex("^🔕 Tắt thông báo$"), disable_notify))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, save_name))

    print("Bot đang chạy...")

    t = threading.Thread(target=auto_loop, args=(app,), daemon=True)
    t.start()

    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
