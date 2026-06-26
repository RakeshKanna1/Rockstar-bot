import logging
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
from config import BOT_TOKEN, ADMIN_ID, WHATSAPP_NUMBER
from gmail_reader import get_latest_code
from database import (
    get_days_remaining,
    get_users,
    get_history,
    init_db,
    get_stats,
    clear_history,
    get_license_expiry,
    generate_license,
    activate_license,
    is_user_active,
    get_admin_stats,
    get_all_user_ids,
    revoke_user,
    extend_license,
    save_user_info
)

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

def register_current_user(update):
    if not update or not update.effective_user:
        return
    user_id = update.effective_user.id
    first_name = update.effective_user.first_name
    username = update.effective_user.username
    try:
        save_user_info(user_id, first_name, username)
    except Exception as e:
        logger.error(f"Error saving user info: {e}")

async def start(update, context):
    register_current_user(update)
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
    # Normal user keyboard (excluding admin monitoring buttons)
    else:
        keyboard = [
            ["📩 Latest Code", "🟢 Status"],
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

    register_current_user(update)
    data = get_users()

    if not data:
        await update.message.reply_text(
            "No users found."
        )
        return

    message = "👥 Rockstar Bot Users List\n\n"
    for user_id, expiry, first_name, username in data:
        name_str = first_name if first_name else "Unknown"
        if username:
            name_str += f" (@{username})"

        # Calculate days remaining or elapsed
        try:
            expiry_date = datetime.strptime(expiry, "%Y-%m-%d").date()
            today = datetime.now().date()
            days = (expiry_date - today).days
        except (ValueError, TypeError):
            days = None

        if days is None:
            status_str = "Unknown Expiry"
        elif days > 0:
            status_str = f"✅ Active (⏳ {days} day{'s' if days > 1 else ''} left)"
        elif days == 0:
            status_str = "⚠️ Expires today!"
        else:
            status_str = f"❌ Expired ({abs(days)} day{'s' if abs(days) > 1 else ''} ago)"

        message += (
            f"👤 **Name**: {name_str}\n"
            f"🆔 **ID**: `{user_id}`\n"
            f"📅 **Expiry**: {expiry}\n"
            f"💡 **Status**: {status_str}\n\n"
        )

    # Chunk output if text exceeds Telegram's limit
    if len(message) > 4000:
        chunks = [message[i:i+4000] for i in range(0, len(message), 4000)]
        for chunk in chunks:
            await update.message.reply_text(chunk, parse_mode="Markdown")
    else:
        await update.message.reply_text(message, parse_mode="Markdown")

async def admin(update, context):
    if update.effective_user.id != ADMIN_ID:
        return

    register_current_user(update)
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

    register_current_user(update)
    if len(context.args) != 2:
        await update.message.reply_text(
            "Usage:\n/extend USER_ID DAYS"
        )
        return

    try:
        user_id = int(context.args[0])
        days = int(context.args[1])
    except ValueError:
        await update.message.reply_text(
            "❌ User ID and Days must be integers."
        )
        return

    expiry = extend_license(user_id, days)

    if not expiry:
        await update.message.reply_text(
            "User not found or has no active license."
        )
        return

    # Notify the specific user about the license extension
    try:
        await context.bot.send_message(
            chat_id=user_id,
            text=(
                f"🎉 **License Extended!**\n\n"
                f"Your license has been extended by **{days} days**.\n"
                f"📅 **New Expiry Date**: `{expiry}`\n\n"
                f"Thank you! 🎮"
            ),
            parse_mode="Markdown"
        )
        notification_status = "User notified successfully."
    except Exception as e:
        logger.warning(f"Failed to send extension notice to user {user_id}: {e}")
        notification_status = "Failed to notify the user (they may have stopped the bot)."

    await update.message.reply_text(
        f"✅ License extended.\n\n"
        f"📅 New Expiry: `{expiry}`\n"
        f"🔔 Status: {notification_status}",
        parse_mode="Markdown"
    )

async def adminhelp(update, context):
    if update.effective_user.id != ADMIN_ID:
        return

    register_current_user(update)
    await update.message.reply_text(
        "🛠 Rakexura Admin Panel Help\n\n"

        "🔑 License Management:\n"
        "• /genkey DAYS - Generate a new key valid for X days\n"
        "• /extend USER_ID DAYS - Extend a user's license by X days\n"
        "• /revoke USER_ID - Revoke access for a user\n\n"

        "👥 User Management:\n"
        "• /users - List all users with active/expired licenses\n"
        "• /admin - View active stats overview\n\n"

        "📢 Communication:\n"
        "• /broadcast MESSAGE - Broadcast a message to all active users\n\n"

        "📊 Monitoring & History:\n"
        "• /license - View your own license info\n"
        "• /stats - View code repository stats\n"
        "• /history - View latest code history\n"
        "• /clearhistory - Clear saved verification codes\n\n"

        "❓ Help:\n"
        "• /adminhelp - Show this panel"
    )

async def revoke(update, context):
    if update.effective_user.id != ADMIN_ID:
        return

    register_current_user(update)
    if len(context.args) != 1:
        await update.message.reply_text(
            "Usage:\n/revoke USER_ID"
        )
        return

    try:
        user_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text(
            "❌ User ID must be an integer."
        )
        return

    revoke_user(user_id)

    await update.message.reply_text(
        f"❌ User {user_id} revoked."
    )

async def broadcast(update, context):
    if update.effective_user.id != ADMIN_ID:
        return

    register_current_user(update)
    if not context.args:
        await update.message.reply_text(
            "Usage:\n/broadcast Your message"
        )
        return

    message = " ".join(context.args)
    users_list = get_all_user_ids()

    sent = 0
    for user_id in users_list:
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=f"📢 Announcement\n\n{message}"
            )
            sent += 1
        except Exception as e:
            logger.warning(f"Failed to broadcast to {user_id}: {e}")

    await update.message.reply_text(
        f"✅ Broadcast sent to {sent} users."
    )

async def license_info(update, context):
    register_current_user(update)
    user_id = update.effective_user.id
    expiry = get_license_expiry(user_id)

    if not expiry:
        await update.message.reply_text(
            f"❌ No active license found.\n\n"
            f"🆔 Your Telegram ID: `{user_id}`",
            parse_mode="Markdown"
        )
        return

    days = get_days_remaining(user_id)

    message = (
        f"🔑 **License Status**\n\n"
        f"🆔 **Your Telegram ID**: `{user_id}`\n"
        f"📅 **Expiry**: `{expiry}`\n"
        f"⏳ **Days Remaining**: {days if days is not None else 0}\n\n"
        f"📲 **Renewal Contact**:\n"
        f"{WHATSAPP_NUMBER}"
    )

    if days is not None and days <= 3:
        message += (
            "\n\n⚠️ **License Expiring Soon!**\n"
            "Please renew to avoid interruption."
        )

    await update.message.reply_text(message, parse_mode="Markdown")

async def check_access(update):
    register_current_user(update)
    user_id = update.effective_user.id

    # Admin bypass
    if user_id == ADMIN_ID:
        return True

    if not is_user_active(user_id):
        await update.message.reply_text(
            "🔒 License Required\n\nSend your license key.\n\nExample:\nRAKEXURA-XXXXXXXX"
        )
        return False

    return True

async def menu_buttons(update, context):
    if not await check_access(update):
        return

    register_current_user(update)
    text = update.message.text

    if text == "📩 Latest Code":
        logger.info(f"Latest Code requested by button from user {update.effective_user.id}")
        code = get_latest_code()
        await update.message.reply_text(
            f"🎮 Latest Rockstar Code:\n\n`{code}`",
            parse_mode="Markdown"
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
        for c in codes:
            message += f"• `{c}`\n"

        await update.message.reply_text(message, parse_mode="Markdown")

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
            f"Latest Code: `{data['latest']}`",
            parse_mode="Markdown"
        )

    elif text == "🟢 Status":
        await update.message.reply_text("🟢 Online")

    elif text == "❓ Help":
        await help_command(update, context)

    elif text == "🔑 License":
        await license_info(update, context)

    elif text == "🛠 Admin Panel":
        if update.effective_user.id != ADMIN_ID:
            return
        await adminhelp(update, context)

async def activate(update, context):
    register_current_user(update)
    if len(context.args) != 1:
        await update.message.reply_text(
            "Usage:\n/activate YOUR_KEY"
        )
        return

    key = context.args[0].strip()

    result = activate_license(key, update.effective_user.id)

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

async def auto_activate(update, context):
    text = update.message.text.strip()

    if not text.startswith("RAKEXURA-"):
        return

    logger.info(f"Auto activation triggered by user {update.effective_user.id} with key: {text}")

    result = activate_license(text, update.effective_user.id)

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

    register_current_user(update)
    if len(context.args) == 0:
        await update.message.reply_text(
            "Usage:\n/genkey 30"
        )
        return

    try:
        days = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Days must be an integer.")
        return

    key = generate_license(days)

    await update.message.reply_text(
        f"🔑 New License Key\n\n`{key}`\n\nValid: {days} days",
        parse_mode="Markdown"
    )

async def test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ Bot is working!")

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🟢 Online")

async def help_command(update, context):
    register_current_user(update)
    user_id = update.effective_user.id
    if user_id == ADMIN_ID:
        await update.message.reply_text(
            "🎮 Rockstar Helper Bot (Admin Mode)\n\n"
            "👤 User Commands:\n"
            "/latestcode - Get latest Rockstar code\n"
            "/license - View active license info\n"
            "/status - Bot status\n"
            "/help - Show this help menu\n\n"
            "🛠 Admin Commands:\n"
            "/admin - View admin dashboard\n"
            "/adminhelp - View complete list of admin commands\n"
            "/users - List active users\n"
            "/history - View previous codes\n"
            "/stats - View statistics\n"
            "/genkey DAYS - Generate new license key\n"
            "/extend USER_ID DAYS - Extend user license\n"
            "/revoke USER_ID - Revoke user license\n"
            "/broadcast MESSAGE - Broadcast announcement to active users\n"
            "/clearhistory - Clear saved codes history"
        )
    else:
        await update.message.reply_text(
            "🎮 Rockstar Helper Bot\n\n"
            "Commands:\n"
            "/latestcode - Get latest Rockstar code\n"
            "/license - View active license info\n"
            "/status - Bot status\n"
            "/help - Show this help menu\n\n"
            "🔑 How to activate license:\n"
            "Send your license key directly in the chat (e.g. RAKEXURA-XXXXXXXX) or use /activate KEY."
        )

async def latestcode(update, context):
    logger.info(f"Latest Code requested by command from user {update.effective_user.id}")

    if not await check_access(update):
        return

    code = get_latest_code()

    await update.message.reply_text(
        f"🎮 Latest Rockstar Code:\n\n`{code}`",
        parse_mode="Markdown"
    )

async def stats(update, context):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text(
            "⛔ Access Denied"
        )
        return

    register_current_user(update)
    data = get_stats()

    await update.message.reply_text(
        f"📊 Rockstar Stats\n\n"
        f"Total Codes Saved: {data['total']}\n"
        f"Latest Code: `{data['latest']}`",
        parse_mode="Markdown"
    )

async def history(update, context):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text(
            "⛔ Access Denied"
        )
        return

    register_current_user(update)
    codes = get_history()

    if not codes:
        await update.message.reply_text(
            "📜 No code history found."
        )
        return

    message = "📜 Rockstar Code History\n\n"
    for code in codes:
        message += f"• `{code}`\n"

    await update.message.reply_text(message, parse_mode="Markdown")

async def clearhistory(update, context):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text(
            "⛔ Access Denied"
        )
        return

    register_current_user(update)
    clear_history()
    await update.message.reply_text("✅ Saved codes history cleared.")

def main():
    # Run DB init to ensure tables exist
    init_db()

    app = Application.builder().token(BOT_TOKEN).build()

    # Commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("test", test))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("latestcode", latestcode))
    app.add_handler(CommandHandler("help", help_command))   
    app.add_handler(CommandHandler("history", history))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("genkey", genkey))
    app.add_handler(CommandHandler("extend", extend))
    app.add_handler(CommandHandler("revoke", revoke))
    app.add_handler(CommandHandler("broadcast", broadcast))
    app.add_handler(CommandHandler("activate", activate))
    app.add_handler(CommandHandler("license", license_info))
    app.add_handler(CommandHandler("admin", admin))
    app.add_handler(CommandHandler("users", users))
    app.add_handler(CommandHandler("adminhelp", adminhelp))
    app.add_handler(CommandHandler("clearhistory", clearhistory))

    # Message handlers
    app.add_handler(MessageHandler(filters.Regex(r"^RAKEXURA-"), auto_activate))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, menu_buttons))

    logger.info("Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
