from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram.ext import MessageHandler, filters
from config import BOT_TOKEN
from config import ADMIN_ID
from config import WHATSAPP_NUMBER
from gmail_reader import get_latest_code
from database import get_days_remaining
from database import get_users
from database import get_history
from database import init_db
from database import get_stats
from database import clear_history
from database import get_license_expiry
from database import generate_license
from database import activate_license
from database import is_user_active
from database import get_admin_stats
from database import get_all_user_ids
from database import revoke_user
from database import extend_license


async def start(update, context):

    user_id = update.effective_user.id
    username = update.effective_user.first_name

    expiry = get_license_expiry(user_id)

    if expiry:
        license_text = f"✅ Active\nExpiry: {expiry}"
    else:
        license_text = "❌ Not Activated"

    # Admin keyboard
    if user_id == ADMIN_ID:

        keyboard = [
            ["📩 Latest Code", "📜 History"],
            ["📊 Stats", "🟢 Status"],
            ["🔑 License", "❓ Help"],
            ["🛠 Admin Panel"]
        ]

    # Normal user keyboard
    else:

        keyboard = [
            ["📩 Latest Code", "📜 History"],
            ["📊 Stats", "🟢 Status"],
            ["🔑 License", "❓ Help"]
        ]

    reply_markup = ReplyKeyboardMarkup(
        keyboard,
        resize_keyboard=True
    )

    await update.message.reply_text(
        f"🎮 Rakexura Rockstar Helper Bot\n\n"
        f"Welcome, {username}! 👋\n\n"
        f"🔑 License Status:\n{license_text}\n\n"
        f"Choose an option below:",
        reply_markup=reply_markup
    )

async def users(update, context):

    if update.effective_user.id != ADMIN_ID:
        return

    data = get_users()

    if not data:
        await update.message.reply_text(
            "No active users found."
        )
        return

    message = "👥 Active Users\n\n"

    for user_id, expiry in data:
        message += (
            f"🆔 {user_id}\n"
            f"🔑 Expiry: {expiry}\n\n"
        )

    await update.message.reply_text(message)

async def admin(update, context):

    if update.effective_user.id != ADMIN_ID:
        return

    data = get_admin_stats()

    await update.message.reply_text(
        f"🛠 Admin Dashboard\n\n"
        f"👥 Active Users: {data['users']}\n"
        f"🔑 Generated Keys: {data['keys']}\n"
        f"📩 Saved Codes: {data['codes']}"
    )

async def extend(update, context):

    if update.effective_user.id != ADMIN_ID:
        return

    if len(context.args) != 2:
        await update.message.reply_text(
            "Usage:\n/extend USER_ID DAYS"
        )
        return

    user_id = int(context.args[0])
    days = int(context.args[1])

    expiry = extend_license(
        user_id,
        days
    )

    if not expiry:
        await update.message.reply_text(
            "User not found."
        )
        return

    await update.message.reply_text(
        f"✅ License extended.\n\nNew Expiry: {expiry}"
    )

async def adminhelp(update, context):

    if update.effective_user.id != ADMIN_ID:
        return

    await update.message.reply_text(
        "🛠 Rakexura Admin Panel\n\n"

        "🔑 License Management\n"
        "/genkey DAYS\n"
        "/extend USER_ID DAYS\n"
        "/revoke USER_ID\n\n"

        "👥 User Management\n"
        "/users\n"
        "/admin\n\n"

        "📢 Communication\n"
        "/broadcast MESSAGE\n\n"

        "📊 Monitoring\n"
        "/license\n"
        "/stats\n\n"

        "❓ Help\n"
        "/adminhelp"
    )

async def revoke(update, context):

    if update.effective_user.id != ADMIN_ID:
        return

    if len(context.args) != 1:
        await update.message.reply_text(
            "Usage:\n/revoke USER_ID"
        )
        return

    user_id = int(context.args[0])

    revoke_user(user_id)

    await update.message.reply_text(
        f"❌ User {user_id} revoked."
    )

async def broadcast(update, context):

    if update.effective_user.id != ADMIN_ID:
        return

    if not context.args:
        await update.message.reply_text(
            "Usage:\n/broadcast Your message"
        )
        return

    message = " ".join(context.args)

    users = get_all_user_ids()

    sent = 0

    for user_id in users:
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=f"📢 Announcement\n\n{message}"
            )
            sent += 1
        except:
            pass

    await update.message.reply_text(
        f"✅ Broadcast sent to {sent} users."
    )

async def license_info(update, context):

    user_id = update.effective_user.id

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT expiry
        FROM licenses
        WHERE used_by = ?
        """,
        (user_id,)
    )

    row = cursor.fetchone()

    conn.close()

    if not row:
        await update.message.reply_text(
            "❌ No active license found."
        )
        return

    await update.message.reply_text(
        f"🔑 License Active\n\nExpiry: {row[0]}"
    )


async def check_access(update):

    user_id = update.effective_user.id

    if not is_user_active(user_id):

        await update.message.reply_text(
            "🔒 License Required\n\nSend your license key.\n\nExample:\nRAKEXURA-XXXXXXXX"
        )

        return False

    return True

async def menu_buttons(update, context):

    if not await check_access(update):
        return

    text = update.message.text

    if text == "📩 Latest Code":

        print("Latest Code button clicked")

        code = get_latest_code()

        print("Returned:", code)

        await update.message.reply_text(
            f"🎮 Latest Rockstar Code:\n\n{code}"
    )

    elif text == "📜 History":

        if update.effective_user.id != ADMIN_ID:
            await update.message.reply_text(
                "⛔ Access Denied"
            )
            return

        codes = get_history()

        if not codes:
            await update.message.reply_text(
                "📜 No code history found."
            )
            return

        message = "📜 Rockstar Code History\n\n"

        for code in codes:
            message += f"• {code}\n"

        await update.message.reply_text(message)

    elif text == "📊 Stats":
        
        if update.effective_user.id != ADMIN_ID:
            await update.message.reply_text(
                "⛔ Access Denied"
            )
            return
        data = get_stats()

        await update.message.reply_text(
            f"📊 Rockstar Stats\n\n"
            f"Total Codes Saved: {data['total']}\n"
            f"Latest Code: {data['latest']}"
        )

    elif text == "🟢 Status":
        await update.message.reply_text("🟢 Online")

    elif text == "❓ Help":
        await update.message.reply_text(
            "Available Features:\n\n"
            "📩 Latest Code\n"
            "📜 History\n"
            "📊 Stats\n"
            "🟢 Status"
        )

    elif text == "🔑 License":

        expiry = get_license_expiry(
            update.effective_user.id
        )
        if expiry:

            days = get_days_remaining(
                update.effective_user.id
            )

            message = (
                f"🔑 License Active\n\n"
                f"Expiry: {expiry}\n"
                f"⏳ Days Remaining: {days}\n\n"
                f"📲 Renewal Contact:\n"
                f"{WHATSAPP_NUMBER}"
            )

            if days <= 3:
                message += (
                    "\n\n⚠️ License Expiring Soon!\n"
                    "Please renew to avoid interruption."
                )

            await update.message.reply_text(message)
        else:
            await update.message.reply_text(
                "❌ No active license found."
        )

        
    elif text == "🛠 Admin Panel":

        if update.effective_user.id != ADMIN_ID:
            return

        await adminhelp(update, context)

    
    

async def activate(update, context):

    if len(context.args) != 1:
        await update.message.reply_text(
            "Usage:\n/activate YOUR_KEY"
        )
        return

    key = context.args[0]

    result = activate_license(
        key,
        update.effective_user.id
    )

    if result == "invalid":
        await update.message.reply_text(
            "❌ Invalid License Key"
        )

    elif result == "used":
        await update.message.reply_text(
            "⚠️ License already used"
        )

    else:
        await update.message.reply_text(
            f"✅ License Activated\n\nValid Until: {result}"
        )

async def auto_activate(update, context):
    

    text = update.message.text.strip()

    

    if not text.startswith("RAKEXURA-"):
        return
    
    print("AUTO ACTIVATION")
    print(text)
    
    result = activate_license(
        text,
        update.effective_user.id
    )

    if result == "invalid":
        await update.message.reply_text(
            "❌ Invalid License Key"
        )

    elif result == "used":
        await update.message.reply_text(
            "⚠️ License already used"
        )

    else:
        await update.message.reply_text(
            f"✅ License Activated\n\nValid Until: {result}"
        )

        await start(update, context)

async def genkey(update, context):

    if update.effective_user.id != ADMIN_ID:
        return

    if len(context.args) == 0:
        await update.message.reply_text(
            "Usage:\n/genkey 30"
        )
        return

    days = int(context.args[0])

    key = generate_license(days)

    await update.message.reply_text(
        f"🔑 New License Key\n\n{key}\n\nValid: {days} days"
    )

async def test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ Bot is working!")

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🟢 Online")

async def help_command(update, context):
    await update.message.reply_text(
        "🎮 Rockstar Helper Bot\n\n"
        "/latestcode - Get latest Rockstar code\n"
        "/history - View previous codes\n"
        "/stats - View statistics\n"
        "/status - Bot status\n"
        "/help - Show this help menu"
    )

async def latestcode(update, context):

    print("Latest Code button pressed")

    if not await check_access(update):
        return

    code = get_latest_code()

    await update.message.reply_text(
        f"🎮 Latest Rockstar Code:\n\n{code}"
    )


async def stats(update, context):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text(
            "⛔ Access Denied"
        )
        return

    data = get_stats()

    await update.message.reply_text(
        f"📊 Rockstar Stats\n\n"
        f"Total Codes Saved: {data['total']}\n"
        f"Latest Code: {data['latest']}"
    )





async def history(update, context):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text(
            "⛔ Access Denied"
        )
        return

    codes = get_history()

    if not codes:
        await update.message.reply_text(
            "📜 No code history found."
        )
        return

    message = "📜 Rockstar Code History\n\n"

    for code in codes:
        message += f"• {code}\n"

    await update.message.reply_text(message)

def main():

    init_db()
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("test", test))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("latestcode", latestcode))
    app.add_handler(CommandHandler("help", help_command))   
    app.add_handler(CommandHandler("history", history))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(
    CommandHandler("genkey", genkey)
)
    app.add_handler(
    MessageHandler(
        filters.Regex(r"^RAKEXURA-"),
        auto_activate
    )
)
    app.add_handler(
    MessageHandler(filters.TEXT & ~filters.COMMAND, menu_buttons)
)
    app.add_handler(
    CommandHandler("activate", activate)
)
    app.add_handler(
    CommandHandler("license", license_info)
)
    app.add_handler(
    CommandHandler("admin", admin)
)
    app.add_handler(
    CommandHandler("users", users)
)
    app.add_handler(
    CommandHandler("broadcast", broadcast)
)
    app.add_handler(
    CommandHandler("revoke", revoke)
)
    app.add_handler(
    CommandHandler("adminhelp", adminhelp)
)
    
    


    print("Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
