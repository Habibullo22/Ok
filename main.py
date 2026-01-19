import os
import sqlite3
from datetime import datetime
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

# ================== SETTINGS ==================
BOT_TOKEN = os.getenv("8353000078:AAH-LOVXzJRMv-twapqwymbPWvGBIZ4vUB4", "PASTE_YOUR_TOKEN_HERE")

# Admin ID(lar)ni shu yerga yoz (Telegram user id)
# Masalan: ADMIN_IDS = {}
ADMIN_IDS = {5815294733}

DB_PATH = "users.db"

# Conversation states
ASK_LOGIN, ASK_SERVER = range(2)

# ================== DB ==================
def db_init():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS connections (
        tg_user_id INTEGER PRIMARY KEY,
        username TEXT,
        first_name TEXT,
        mt5_login TEXT,
        mt5_server TEXT,
        status TEXT,
        updated_at TEXT
    )
    """)
    conn.commit()
    conn.close()

def db_upsert_request(tg_user_id: int, username: str, first_name: str, mt5_login: str, mt5_server: str, status: str):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
    INSERT INTO connections (tg_user_id, username, first_name, mt5_login, mt5_server, status, updated_at)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(tg_user_id) DO UPDATE SET
        username=excluded.username,
        first_name=excluded.first_name,
        mt5_login=excluded.mt5_login,
        mt5_server=excluded.mt5_server,
        status=excluded.status,
        updated_at=excluded.updated_at
    """, (tg_user_id, username, first_name, mt5_login, mt5_server, status, datetime.utcnow().isoformat()))
    conn.commit()
    conn.close()

def db_update_status(tg_user_id: int, status: str):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
    UPDATE connections
    SET status=?, updated_at=?
    WHERE tg_user_id=?
    """, (status, datetime.utcnow().isoformat(), tg_user_id))
    conn.commit()
    conn.close()

def db_get(tg_user_id: int):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT tg_user_id, username, first_name, mt5_login, mt5_server, status, updated_at FROM connections WHERE tg_user_id=?", (tg_user_id,))
    row = cur.fetchone()
    conn.close()
    return row

# ================== HELPERS ==================
def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

def fmt_user(u):
    uname = f"@{u.username}" if u.username else "(username yo‘q)"
    return f"{uname} | ID: {u.id} | Name: {u.first_name or ''}"

def approval_keyboard(tg_user_id: int):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Tasdiqlash", callback_data=f"approve:{tg_user_id}"),
            InlineKeyboardButton("❌ Rad etish", callback_data=f"reject:{tg_user_id}")
        ]
    ])

# ================== COMMANDS ==================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "✅ Signal bot / ulanish tizimi ishga tushdi.\n\n"
        "User uchun komandalar:\n"
        "• /connect — MT5 login+server yuborish (parol YO‘Q)\n"
        "• /status — holatni ko‘rish\n\n"
        "Admin uchun:\n"
        "• /pending — kutilayotganlarni ko‘rish (keyin qo‘shamiz)\n\n"
        "Eslatma: xavfsizlik uchun bot HECH QACHON MT5 parol so‘ramaydi."
    )

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    row = db_get(update.effective_user.id)
    if not row:
        await update.message.reply_text("ℹ️ Siz hali /connect qilmagansiz.")
        return
    _, username, first_name, mt5_login, mt5_server, st, upd = row
    await update.message.reply_text(
        f"📌 Sizning holatingiz:\n"
        f"👤 {('@'+username) if username else first_name}\n"
        f"🔢 MT5 login: {mt5_login}\n"
        f"🏦 Server: {mt5_server}\n"
        f"📍 Status: {st}\n"
        f"🕒 Updated: {upd}"
    )

# ================== CONNECT FLOW ==================
async def connect_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🔐 Ulanish (XAVFSIZ):\n\n"
        "MT5 login raqamingizni yuboring (faqat raqam).\n"
        "❗️Parol yubormang."
    )
    return ASK_LOGIN

async def connect_login(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = (update.message.text or "").strip()
    if not txt.isdigit() or len(txt) < 5:
        await update.message.reply_text("❌ Login faqat raqam bo‘lsin (masalan: 12345678). Qayta yuboring:")
        return ASK_LOGIN

    context.user_data["mt5_login"] = txt
    await update.message.reply_text(
        "🏦 Endi MT5 server nomini yuboring.\n"
        "Misol: XMGlobal-Real 12 yoki RoboForex-ECN"
    )
    return ASK_SERVER

async def connect_server(update: Update, context: ContextTypes.DEFAULT_TYPE):
    server = (update.message.text or "").strip()
    if len(server) < 3:
        await update.message.reply_text("❌ Server nomi juda qisqa. Qayta yuboring:")
        return ASK_SERVER

    u = update.effective_user
    mt5_login = context.user_data.get("mt5_login")

    # DB: pending
    db_upsert_request(
        tg_user_id=u.id,
        username=u.username or "",
        first_name=u.first_name or "",
        mt5_login=mt5_login,
        mt5_server=server,
        status="pending"
    )

    # Send to admins
    text = (
        "🆕 ULANISH SO‘ROVI (PENDING)\n\n"
        f"👤 User: {fmt_user(u)}\n"
        f"🔢 MT5 login: {mt5_login}\n"
        f"🏦 Server: {server}\n\n"
        "Tasdiqlaysizmi?"
    )
    kb = approval_keyboard(u.id)

    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_message(chat_id=admin_id, text=text, reply_markup=kb)
        except Exception:
            pass

    await update.message.reply_text(
        "✅ So‘rov yuborildi.\n"
        "Admin ko‘rib chiqadi. /status orqali tekshirib turing."
    )
    return ConversationHandler.END

async def connect_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Bekor qilindi.")
    return ConversationHandler.END

# ================== ADMIN CALLBACKS ==================
async def on_admin_decision(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not is_admin(query.from_user.id):
        await query.edit_message_text("❌ Siz admin emassiz.")
        return

    data = query.data  # approve:123 or reject:123
    action, user_id_str = data.split(":", 1)
    target_id = int(user_id_str)

    row = db_get(target_id)
    if not row:
        await query.edit_message_text("⚠️ Bu user bo‘yicha so‘rov topilmadi.")
        return

    _, username, first_name, mt5_login, mt5_server, st, upd = row

    if action == "approve":
        db_update_status(target_id, "approved")
        await query.edit_message_text(
            "✅ TASDIQLANDI\n\n"
            f"👤 {('@'+username) if username else first_name} | ID: {target_id}\n"
            f"🔢 {mt5_login}\n🏦 {mt5_server}"
        )
        try:
            await context.bot.send_message(
                chat_id=target_id,
                text="✅ Admin sizni TASDIQLADI. Endi signal xizmatidan foydalanishingiz mumkin."
            )
        except Exception:
            pass

    elif action == "reject":
        db_update_status(target_id, "rejected")
        await query.edit_message_text(
            "❌ RAD ETILDI\n\n"
            f"👤 {('@'+username) if username else first_name} | ID: {target_id}\n"
            f"🔢 {mt5_login}\n🏦 {mt5_server}"
        )
        try:
            await context.bot.send_message(
                chat_id=target_id,
                text="❌ Admin so‘rovingizni RAD ETDI. Qayta /connect qilib urinib ko‘rishingiz mumkin."
            )
        except Exception:
            pass

# ================== RUN ==================
def main():
    db_init()
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("status", status))

    conv = ConversationHandler(
        entry_points=[CommandHandler("connect", connect_start)],
        states={
            ASK_LOGIN: [MessageHandler(filters.TEXT & ~filters.COMMAND, connect_login)],
            ASK_SERVER: [MessageHandler(filters.TEXT & ~filters.COMMAND, connect_server)],
        },
        fallbacks=[CommandHandler("cancel", connect_cancel)],
    )
    app.add_handler(conv)

    app.add_handler(CallbackQueryHandler(on_admin_decision, pattern=r"^(approve|reject):"))

    print("Bot running...")
    app.run_polling(close_loop=False)

if __name__ == "__main__":
    main()
