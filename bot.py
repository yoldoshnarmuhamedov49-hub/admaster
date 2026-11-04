import os
import re
import json
import sqlite3
import logging
from datetime import datetime

from telegram import (
    Update,
    ReplyKeyboardMarkup,
    KeyboardButton,
    WebAppInfo,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("admaster")

# =========================
# SOZLAMALAR (muhit o'zgaruvchilaridan)
# =========================

TOKEN = os.environ["BOT_TOKEN"]
ADMIN_ID = int(os.environ["ADMIN_ID"])
WEBAPP_URL = os.environ.get("WEBAPP_URL", "")
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "@admin")
CARD_NUMBER = os.environ.get("CARD_NUMBER", "")
CARD_OWNER = os.environ.get("CARD_OWNER", "")

DB_NAME = "admaster.db"

TARIFFS = {
    "START": 10_000,
    "STANDART": 25_000,
    "PREMIUM": 50_000,
    "VIP": 100_000,
}

# =========================
# DATABASE
# =========================

def connect():
    return sqlite3.connect(DB_NAME)


def init_db():
    con = connect()
    cur = con.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users(
            user_id INTEGER PRIMARY KEY,
            balance INTEGER DEFAULT 0
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS payments(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            amount INTEGER,
            status TEXT DEFAULT 'pending',
            created_at TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS orders(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            description TEXT,
            status TEXT DEFAULT 'new',
            created_at TEXT
        )
    """)
    con.commit()
    con.close()


def register_user(uid: int):
    con = connect()
    con.execute("INSERT OR IGNORE INTO users(user_id) VALUES(?)", (uid,))
    con.commit()
    con.close()


def get_balance(uid: int) -> int:
    con = connect()
    row = con.execute("SELECT balance FROM users WHERE user_id=?", (uid,)).fetchone()
    con.close()
    return row[0] if row else 0


def fmt(amount: int) -> str:
    return f"{amount:,}".replace(",", " ") + " so'm"

# =========================
# MENU
# =========================

MENU_ROWS = [
    ["📢 Reklama berish"],
    ["💳 Balans to'ldirish", "💰 Mening balansim"],
    ["📋 Tariflar", "👤 Profil"],
    ["📞 Yordam"],
]
MENU_BUTTONS = {b for row in MENU_ROWS for b in row} | {"🚀 ADMASTER ilovasini ochish"}


def keyboard() -> ReplyKeyboardMarkup:
    rows = []
    if WEBAPP_URL:
        rows.append([KeyboardButton("🚀 ADMASTER ilovasini ochish",
                                    web_app=WebAppInfo(url=WEBAPP_URL))])
    rows += [[KeyboardButton(b) for b in row] for row in MENU_ROWS]
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)

# =========================
# COMMANDS
# =========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    register_user(update.effective_user.id)
    context.user_data.clear()
    await update.message.reply_text(
        "🚀 ADMASTER AUTO\n\nReklama platformasiga xush kelibsiz!",
        reply_markup=keyboard(),
    )


async def myid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"🆔 ID: {update.effective_user.id}")


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("Bekor qilindi.", reply_markup=keyboard())


async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("Ruxsat yo'q!")
        return

    con = connect()
    users = con.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    pending = con.execute("SELECT COUNT(*) FROM payments WHERE status='pending'").fetchone()[0]
    orders = con.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
    con.close()

    await update.message.reply_text(
        "👨‍💻 ADMASTER ADMIN PANEL\n\n"
        f"👥 Foydalanuvchilar: {users}\n"
        f"💳 Kutilayotgan to'lovlar: {pending}\n"
        f"📢 Buyurtmalar: {orders}"
    )

# =========================
# MENU TEXT HANDLER
# =========================

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    text = update.message.text.strip()

    # Menyu tugmasi bosilsa, oldingi kutilayotgan holatni bekor qilamiz
    if text in MENU_BUTTONS:
        context.user_data.clear()

        if text == "📢 Reklama berish":
            context.user_data["waiting_order"] = True
            await update.message.reply_text(
                "📢 Reklama matni yoki havolasini yuboring."
            )
        elif text == "💳 Balans to'ldirish":
            context.user_data["waiting_amount"] = True
            await update.message.reply_text(
                "💳 Qancha pul to'ldirmoqchisiz?\nMasalan: 50000"
            )
        elif text == "💰 Mening balansim":
            await update.message.reply_text(f"💰 Balans: {fmt(get_balance(uid))}")
        elif text == "📋 Tariflar":
            lines = [f"{name}: {fmt(price)}" for name, price in TARIFFS.items()]
            await update.message.reply_text("\n".join(lines))
        elif text == "👤 Profil":
            await update.message.reply_text(
                f"👤 PROFIL\nID: {uid}\nBalans: {fmt(get_balance(uid))}"
            )
        elif text == "📞 Yordam":
            await update.message.reply_text(f"Admin: {ADMIN_USERNAME}")
        return

    # Chek kutilayotgan bo'lsa, matn o'rniga rasm kerak
    if context.user_data.get("waiting_receipt"):
        await update.message.reply_text("Iltimos, chek rasmini yuboring.")
        return

    # Summa kutilayotgan bo'lsa
    if context.user_data.get("waiting_amount"):
        if not text.isdigit():
            await update.message.reply_text("Faqat raqam yuboring.")
            return

        amount = int(text)
        if not 1000 <= amount <= 100_000_000:
            await update.message.reply_text("Noto'g'ri summa. 1 000 dan 100 000 000 gacha kiriting.")
            return

        if not CARD_NUMBER:
            await update.message.reply_text("To'lov kartasi hali sozlanmagan. Admin bilan bog'laning.")
            return

        context.user_data["waiting_amount"] = False
        context.user_data["payment_amount"] = amount
        context.user_data["waiting_receipt"] = True

        await update.message.reply_text(
            f"💳 KARTA: {CARD_NUMBER}\n"
            f"Egasi: {CARD_OWNER}\n"
            f"Summa: {fmt(amount)}\n\n"
            "To'lovdan keyin chek rasmini yuboring."
        )
        return

    # Reklama buyurtmasi kutilayotgan bo'lsa
    if context.user_data.get("waiting_order"):
        con = connect()
        cur = con.execute(
            "INSERT INTO orders(user_id, description, created_at) VALUES(?,?,?)",
            (uid, text, datetime.now().isoformat()),
        )
        order_id = cur.lastrowid
        con.commit()
        con.close()

        context.user_data.clear()

        await context.bot.send_message(
            ADMIN_ID,
            f"📢 YANGI BUYURTMA #{order_id}\nFoydalanuvchi: {uid}\n\n{text}",
        )
        await update.message.reply_text("✅ Buyurtma qabul qilindi.", reply_markup=keyboard())
        return

    await update.message.reply_text("Menyudan tanlang.", reply_markup=keyboard())

# =========================
# WEB APP DATA (mini ilovadan kelgan buyurtma)
# =========================

async def web_app_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    try:
        data = json.loads(update.message.web_app_data.data)
    except (json.JSONDecodeError, TypeError):
        await update.message.reply_text("Xatolik: ma'lumot noto'g'ri formatda.")
        return

    channel = str(data.get("channel", "-"))
    plan = str(data.get("plan", "-"))
    text = str(data.get("text", "-"))

    description = f"Kanal: {channel}\nTarif: {plan}\nMatn: {text}"

    con = connect()
    cur = con.execute(
        "INSERT INTO orders(user_id, description, created_at) VALUES(?,?,?)",
        (user.id, description, datetime.now().isoformat()),
    )
    order_id = cur.lastrowid
    con.commit()
    con.close()

    log.info("Web App buyurtma #%s: user=%s plan=%s", order_id, user.id, plan)

    await context.bot.send_message(
        ADMIN_ID,
        f"🆕 YANGI BUYURTMA #{order_id} (Web App)\n"
        f"Mijoz: {user.full_name} (ID: {user.id})\n\n"
        f"{description}\nNarx: {fmt(TARIFFS.get(plan, 0))}",
    )
    await update.message.reply_text(
        "✅ Buyurtmangiz qabul qilindi! Administrator tez orada bog'lanadi.",
        reply_markup=keyboard(),
    )

# =========================
# RECEIPT (chek rasmi)
# =========================

async def receipt_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("waiting_receipt"):
        await update.message.reply_text(
            "Avval menyudan «💳 Balans to'ldirish» ni tanlang.",
            reply_markup=keyboard(),
        )
        return

    uid = update.effective_user.id
    amount = context.user_data.get("payment_amount")

    con = connect()
    cur = con.execute(
        "INSERT INTO payments(user_id, amount, created_at) VALUES(?,?,?)",
        (uid, amount, datetime.now().isoformat()),
    )
    payment_id = cur.lastrowid
    con.commit()
    con.close()

    context.user_data.clear()

    buttons = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Tasdiqlash", callback_data=f"approve:{payment_id}"),
        InlineKeyboardButton("❌ Rad etish", callback_data=f"reject:{payment_id}"),
    ]])

    await context.bot.send_photo(
        ADMIN_ID,
        update.message.photo[-1].file_id,
        caption=f"🧾 TO'LOV #{payment_id}\nID: {uid}\nSumma: {fmt(amount)}",
        reply_markup=buttons,
    )
    await update.message.reply_text(
        "✅ Chek adminga yuborildi. Tekshiruv kutilmoqda.",
        reply_markup=keyboard(),
    )

# =========================
# ADMIN: TO'LOVNI TASDIQLASH / RAD ETISH
# =========================

async def payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    if query.from_user.id != ADMIN_ID:
        await query.answer("Admin emassiz!", show_alert=True)
        return

    match = re.fullmatch(r"(approve|reject):(\d+)", query.data or "")
    if not match:
        await query.answer("Xato!")
        return

    action, pid = match.group(1), int(match.group(2))

    con = connect()
    row = con.execute(
        "SELECT user_id, amount, status FROM payments WHERE id=?", (pid,)
    ).fetchone()

    if not row:
        con.close()
        await query.answer("To'lov topilmadi.")
        return

    uid, amount, status = row
    if status != "pending":
        con.close()
        await query.answer("Bu to'lov allaqachon ko'rilgan.", show_alert=True)
        return

    if action == "approve":
        new_status = "approved"
    else:
        new_status = "rejected"

    # Shartli yangilash: ikki admin bir vaqtda bossa ham faqat bir marta ishlaydi
    cur = con.execute(
        "UPDATE payments SET status=? WHERE id=? AND status='pending'",
        (new_status, pid),
    )
    if cur.rowcount != 1:
        con.close()
        await query.answer("Bu to'lov allaqachon ko'rilgan.", show_alert=True)
        return

    if action == "approve":
        con.execute("INSERT OR IGNORE INTO users(user_id) VALUES(?)", (uid,))
        con.execute(
            "UPDATE users SET balance = balance + ? WHERE user_id=?",
            (amount, uid),
        )
        message = "✅ TO'LOV TASDIQLANDI"
    else:
        message = "❌ TO'LOV RAD ETILDI"

    con.commit()
    con.close()

    await query.answer("Bajarildi!")
    await query.edit_message_caption(
        caption=f"{message}\nID: {uid}\nSumma: {fmt(amount)}",
        reply_markup=None,
    )

    try:
        if action == "approve":
            await context.bot.send_message(
                uid,
                f"✅ To'lov tasdiqlandi!\nBalansingizga {fmt(amount)} qo'shildi.",
            )
        else:
            await context.bot.send_message(
                uid,
                f"❌ To'lov rad etildi. Savol bo'lsa {ADMIN_USERNAME} ga yozing.",
            )
    except Exception as e:
        log.warning("Foydalanuvchiga xabar yuborib bo'lmadi (%s): %s", uid, e)

# =========================
# MAIN
# =========================

def main():
    init_db()

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("myid", myid))
    app.add_handler(CommandHandler("admin", admin))
    app.add_handler(CommandHandler("cancel", cancel))

    app.add_handler(CallbackQueryHandler(payment_callback))
    app.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, web_app_data))
    app.add_handler(MessageHandler(filters.PHOTO, receipt_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    log.info("ADMASTER AUTO ishga tushdi!")
    app.run_polling()


if __name__ == "__main__":
    main()
