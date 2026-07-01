import logging
import os
import asyncio
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters, CallbackQueryHandler
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
    save_user_info,
    find_user_by_username,
    get_user_details
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

def format_users_list(data):
    if not data:
        return "No users found."

    active_users = []
    expired_users = []

    for user_id, expiry, first_name, username, activated_keys in data:
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

        keys_str = activated_keys if activated_keys else "None"

        if days is None:
            status_str = "Unknown Expiry"
            expired_users.append((name_str, user_id, expiry, status_str, keys_str))
        elif days > 0:
            status_str = f"⏳ {days} day{'s' if days > 1 else ''} left"
            active_users.append((name_str, user_id, expiry, status_str, keys_str))
        elif days == 0:
            status_str = "⚠️ Expires today!"
            active_users.append((name_str, user_id, expiry, status_str, keys_str))
        else:
            status_str = f"❌ Expired ({abs(days)} day{'s' if abs(days) > 1 else ''} ago)"
            expired_users.append((name_str, user_id, expiry, status_str, keys_str))

    message = "👥 **Rockstar Bot Users Directory**\n\n"

    if active_users:
        message += "🟢 **ACTIVE LICENSES**\n"
        message += "---------------------\n"
        for idx, (name, u_id, exp, status, keys) in enumerate(active_users, 1):
            message += (
                f"{idx}. **{name}**\n"
                f"   🆔 ID: `{u_id}`\n"
                f"   🔑 Key(s): `{keys}`\n"
                f"   📅 Expiry: `{exp}` ({status})\n\n"
            )

    if expired_users:
        message += "🔴 **EXPIRED LICENSES**\n"
        message += "----------------------\n"
        for idx, (name, u_id, exp, status, keys) in enumerate(expired_users, 1):
            message += (
                f"{idx}. **{name}**\n"
                f"   🆔 ID: `{u_id}`\n"
                f"   🔑 Key(s): `{keys}`\n"
                f"   📅 Expiry: `{exp}` ({status})\n\n"
            )

    return message

async def users(update, context):
    if update.effective_user.id != ADMIN_ID:
        return

    register_current_user(update)
    data = get_users()
    message = format_users_list(data)

    # Chunk output if text exceeds Telegram's limit
    if len(message) > 4000:
        chunks = [message[i:i+4000] for i in range(0, len(message), 4000)]
        for chunk in chunks:
            await update.message.reply_text(chunk, parse_mode="Markdown")
    else:
        await update.message.reply_text(message, parse_mode="Markdown")

async def user_command(update, context):
    if update.effective_user.id != ADMIN_ID:
        return

    register_current_user(update)

    if not context.args:
        await update.message.reply_text(
            "Usage:\n"
            "• `/user USER_ID` - Get info for a specific user ID\n"
            "• `/user @username` - Get info for a specific username\n"
            "• Use `/users` to list all users",
            parse_mode="Markdown"
        )
        return

    query = context.args[0]
    user_id = None

    # Check if username query
    if query.startswith("@") or not query.isdigit():
        username = query.lstrip("@")
        user_id = find_user_by_username(username)
        if not user_id:
            await update.message.reply_text(f"❌ User with username `@{username}` not found in database.", parse_mode="Markdown")
            return
    else:
        try:
            user_id = int(query)
        except ValueError:
            await update.message.reply_text("❌ User ID must be a number or a valid username starting with @.")
            return

    details = get_user_details(user_id)

    if not details:
        await update.message.reply_text(f"❌ No records found for User ID `{user_id}`.", parse_mode="Markdown")
        return

    first_name, username, last_seen = details["profile"] if details["profile"] else ("Unknown", None, "Never")
    licenses = details["licenses"]

    name_str = first_name
    if username:
        name_str += f" (@{username})"

    # Get active expiry
    expiry = get_license_expiry(user_id)
    if expiry:
        days = get_days_remaining(user_id)
        if days is None:
            status_str = "Unknown Expiry"
        elif days > 0:
            status_str = f"✅ Active (⏳ {days} day{'s' if days > 1 else ''} left)"
        elif days == 0:
            status_str = "⚠️ Expires today!"
        else:
            status_str = f"❌ Expired ({abs(days)} day{'s' if abs(days) > 1 else ''} ago)"
    else:
        status_str = "❌ No active license found"

    message = (
        f"👤 **User Profile**\n"
        f"• **Name**: {name_str}\n"
        f"• **ID**: `{user_id}`\n"
        f"• **Last Seen**: `{last_seen}`\n"
        f"• **Status**: {status_str}\n"
        f"• **License Expiry**: `{expiry or 'None'}`\n\n"
        f"🔑 **License Keys History**:\n"
    )

    if not licenses:
        message += "No licenses activated yet."
    else:
        for key, days_count, exp, used in licenses:
            message += f"• `{key}` ({days_count} days) · Expiry: {exp or 'None'} · Used: {'Yes' if used else 'No'}\n"

    keyboard = [
        [
            InlineKeyboardButton("⏳ +7 Days", callback_data=f"extend:{user_id}:7"),
            InlineKeyboardButton("⏳ +30 Days", callback_data=f"extend:{user_id}:30"),
        ],
        [
            InlineKeyboardButton("❌ Revoke", callback_data=f"revoke:{user_id}"),
            InlineKeyboardButton("🔄 Refresh", callback_data=f"detail:{user_id}"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(message, parse_mode="Markdown", reply_markup=reply_markup)

async def show_user_detail_callback(query, user_id):
    details = get_user_details(user_id)
    if not details:
        await query.edit_message_text(f"❌ User ID `{user_id}` not found.")
        return

    first_name, username, last_seen = details["profile"] if details["profile"] else ("Unknown", None, "Never")
    licenses = details["licenses"]

    name_str = first_name
    if username:
        name_str += f" (@{username})"

    expiry = get_license_expiry(user_id)
    if expiry:
        days = get_days_remaining(user_id)
        if days is None:
            status_str = "Unknown Expiry"
        elif days > 0:
            status_str = f"✅ Active (⏳ {days} day{'s' if days > 1 else ''} left)"
        elif days == 0:
            status_str = "⚠️ Expires today!"
        else:
            status_str = f"❌ Expired ({abs(days)} day{'s' if abs(days) > 1 else ''} ago)"
    else:
        status_str = "❌ No active license found"

    message = (
        f"👤 **User Profile**\n"
        f"• **Name**: {name_str}\n"
        f"• **ID**: `{user_id}`\n"
        f"• **Last Seen**: `{last_seen}`\n"
        f"• **Status**: {status_str}\n"
        f"• **License Expiry**: `{expiry or 'None'}`\n\n"
        f"🔑 **License Keys History**:\n"
    )

    if not licenses:
        message += "No licenses activated yet."
    else:
        for key, days_count, exp, used in licenses:
            message += f"• `{key}` ({days_count} days) · Expiry: {exp or 'None'} · Used: {'Yes' if used else 'No'}\n"

    keyboard = [
        [
            InlineKeyboardButton("⏳ +7 Days", callback_data=f"extend:{user_id}:7"),
            InlineKeyboardButton("⏳ +30 Days", callback_data=f"extend:{user_id}:30"),
        ],
        [
            InlineKeyboardButton("❌ Revoke", callback_data=f"revoke:{user_id}"),
            InlineKeyboardButton("🔄 Refresh", callback_data=f"detail:{user_id}"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(message, parse_mode="Markdown", reply_markup=reply_markup)

async def admin_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if update.effective_user.id != ADMIN_ID:
        return

    data = query.data.split(":")
    action = data[0]

    # Handle global admin actions that don't need a specific user_id
    if action == "admin_genkey_menu":
        keyboard = [
            [
                InlineKeyboardButton("1 Day", callback_data="admin_genkey_exec:1"),
                InlineKeyboardButton("7 Days", callback_data="admin_genkey_exec:7"),
            ],
            [
                InlineKeyboardButton("30 Days", callback_data="admin_genkey_exec:30"),
                InlineKeyboardButton("90 Days", callback_data="admin_genkey_exec:90"),
            ],
            [
                InlineKeyboardButton("365 Days", callback_data="admin_genkey_exec:365"),
            ],
            [
                InlineKeyboardButton("⬅️ Back to Admin", callback_data="admin_menu")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "🔑 **Select Key Duration**\n\nChoose the duration for the new license key:",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
        return

    elif action == "admin_genkey_exec":
        days = int(data[1])
        key = generate_license(days)
        keyboard = [
            [InlineKeyboardButton("⬅️ Back to Admin", callback_data="admin_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            f"🔑 **License Key Generated!**\n\n"
            f"Key: `{key}`\n"
            f"Duration: **{days} days**\n\n"
            f"Share this key with the user.",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
        return

    elif action == "admin_menu":
        data_stats = get_admin_stats()
        keyboard = [
            [
                InlineKeyboardButton("🔑 Gen Key", callback_data="admin_genkey_menu"),
                InlineKeyboardButton("👥 Users List", callback_data="admin_users"),
            ],
            [
                InlineKeyboardButton("💾 Backup DB", callback_data="admin_backup"),
                InlineKeyboardButton("📩 Latest Code", callback_data="admin_latest"),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            f"🛠 Admin Dashboard\n\n"
            f"👥 Active Users: {data_stats['users']}\n"
            f"🔑 Generated Keys: {data_stats['keys']}\n"
            f"📩 Saved Codes: {data_stats['codes']}",
            reply_markup=reply_markup
        )
        return

    elif action == "admin_users":
        data_users = get_users()
        keyboard = [
            [InlineKeyboardButton("⬅️ Back to Admin", callback_data="admin_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        message = format_users_list(data_users)

        if len(message) > 4000:
            message = message[:3900] + "\n... (Truncated due to length)"
        
        await query.edit_message_text(message, parse_mode="Markdown", reply_markup=reply_markup)
        return

    elif action == "admin_backup":
        keyboard = [
            [InlineKeyboardButton("⬅️ Back to Admin", callback_data="admin_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        if not os.path.exists("database.db"):
            await query.edit_message_text("❌ database.db file not found.", reply_markup=reply_markup)
            return

        try:
            with open("database.db", "rb") as f:
                await context.bot.send_document(
                    chat_id=update.effective_chat.id,
                    document=f,
                    filename="database_backup.db",
                    caption="💾 Rockstar Bot SQLite Database Backup"
                )
            await query.edit_message_text("✅ Backup sent successfully to this chat!", reply_markup=reply_markup)
        except Exception as e:
            await query.edit_message_text(f"❌ Failed to send backup: {e}", reply_markup=reply_markup)
        return

    elif action == "admin_latest":
        code = get_latest_code()
        keyboard = [
            [InlineKeyboardButton("⬅️ Back to Admin", callback_data="admin_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(f"🎮 Latest Rockstar Code:\n\n`{code}`", parse_mode="Markdown", reply_markup=reply_markup)
        return

    user_id = int(data[1])

    if action == "extend":
        days = int(data[2])
        from database import extend_license
        expiry = extend_license(user_id, days)
        if not expiry:
            await query.edit_message_text("❌ Failed to extend license. User not found.")
            return

        # Notify the user
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
            notify_str = "User notified successfully."
        except Exception as e:
            notify_str = f"Failed to notify user: {e}"

        await query.edit_message_text(
            f"✅ License extended by **{days} days** for User `{user_id}`.\n"
            f"📅 New Expiry: `{expiry}`\n"
            f"🔔 Notification: {notify_str}",
            parse_mode="Markdown"
        )

    elif action == "revoke":
        from database import revoke_user
        revoke_user(user_id)
        await query.edit_message_text(
            f"❌ License access for User `{user_id}` has been revoked.",
            parse_mode="Markdown"
        )

    elif action == "detail":
        await show_user_detail_callback(query, user_id)

async def backup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    register_current_user(update)

    if not os.path.exists("database.db"):
        await update.message.reply_text("❌ database.db file not found.")
        return

    await update.message.reply_text("📤 Backing up database... sending file...")
    try:
        with open("database.db", "rb") as f:
            await context.bot.send_document(
                chat_id=update.effective_chat.id,
                document=f,
                filename="database_backup.db",
                caption="💾 Rockstar Bot SQLite Database Backup"
            )
    except Exception as e:
        await update.message.reply_text(f"❌ Failed to send database backup: {e}")

async def check_expired_licenses_loop(app):
    await asyncio.sleep(10) # Initial wait for bot to start up
    while True:
        try:
            logger.info("Running background license expiry check...")
            from datetime import datetime, timedelta
            import sqlite3
            
            conn = sqlite3.connect("database.db")
            cursor = conn.cursor()
            
            # Find all users whose latest license has expired
            today = datetime.now().strftime("%Y-%m-%d")
            cursor.execute("""
                SELECT used_by, max_expiry
                FROM (
                    SELECT used_by, MAX(expiry) as max_expiry
                    FROM licenses
                    WHERE used = 1 AND used_by IS NOT NULL
                    GROUP BY used_by
                )
                WHERE max_expiry < ?
            """, (today,))
            
            expired_users = cursor.fetchall()

            # Find active users who have not interacted with the bot for more than 5 days
            inactive_cutoff = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute("""
                SELECT l.used_by, u.last_seen, MAX(l.expiry) as max_expiry
                FROM licenses l
                JOIN users u ON l.used_by = u.user_id
                WHERE l.used = 1
                  AND l.used_by IS NOT NULL
                  AND l.expiry >= ?
                  AND u.last_seen IS NOT NULL
                  AND u.last_seen < ?
                GROUP BY l.used_by
            """, (today, inactive_cutoff))

            inactive_users = cursor.fetchall()
            conn.close()
            
            for user_id, expiry in expired_users:
                # 1. Revoke in database
                from database import revoke_user
                revoke_user(user_id)
                logger.info(f"Automatically revoked expired license for user {user_id} (expired {expiry})")
                
                # 2. Get user's profile details to show username
                from database import get_user_details
                details = get_user_details(user_id)
                username = None
                first_name = "User"
                if details and details["profile"]:
                    first_name, username, _ = details["profile"]
                
                name_str = first_name
                if username:
                    name_str += f" (@{username})"

                # 3. Message the user
                try:
                    await app.bot.send_message(
                        chat_id=user_id,
                        text=(
                            f"⚠️ **License Expired!**\n\n"
                            f"Hello {first_name}, your Rakexura Rockstar license key expired on `{expiry}`.\n"
                            f"Access to bot features has been automatically revoked.\n\n"
                            f"📲 To renew your license, contact: {WHATSAPP_NUMBER}\n"
                            f"Thank you for choosing Rakexura! 🎮"
                        ),
                        parse_mode="Markdown"
                    )
                except Exception as e:
                    logger.warning(f"Failed to notify user {user_id} about license expiry: {e}")

                # 4. Message the admin
                try:
                    await app.bot.send_message(
                        chat_id=ADMIN_ID,
                        text=(
                            f"⚠️ **License Expired & Revoked**\n\n"
                            f"• **User**: {name_str}\n"
                            f"• **ID**: `{user_id}`\n"
                            f"• **Expired Date**: `{expiry}`\n"
                            f"Successfully notified and status updated to Revoked."
                        ),
                        parse_mode="Markdown"
                    )
                except Exception as e:
                    logger.warning(f"Failed to send admin notification for user {user_id} expiry: {e}")

            for user_id, last_seen, expiry in inactive_users:
                from database import revoke_user, get_user_details
                details = get_user_details(user_id)
                username = None
                first_name = "User"
                if details and details["profile"]:
                    first_name, username, _ = details["profile"]

                name_str = first_name
                if username:
                    name_str += f" (@{username})"

                revoke_user(user_id)
                logger.info(f"Automatically revoked inactive user {user_id} (last seen {last_seen})")

                try:
                    await app.bot.send_message(
                        chat_id=user_id,
                        text=(
                            f"⚠️ **License Revoked Due to Inactivity**\n\n"
                            f"Hello {first_name}, your Rakexura Rockstar license was revoked because "
                            f"you were inactive for more than 5 days.\n\n"
                            f"📲 To reactivate or renew, contact: {WHATSAPP_NUMBER}"
                        ),
                        parse_mode="Markdown"
                    )
                except Exception as e:
                    logger.warning(f"Failed to notify inactive user {user_id}: {e}")

                try:
                    await app.bot.send_message(
                        chat_id=ADMIN_ID,
                        text=(
                            f"⚠️ **Inactive User Revoked**\n\n"
                            f"• **User**: {name_str}\n"
                            f"• **ID**: `{user_id}`\n"
                            f"• **Last Seen**: `{last_seen}`\n"
                            f"• **License Expiry Was**: `{expiry}`\n"
                            f"User was inactive for more than 5 days."
                        ),
                        parse_mode="Markdown"
                    )
                except Exception as e:
                    logger.warning(f"Failed to send admin notification for inactive user {user_id}: {e}")

        except Exception as e:
            logger.error(f"Error in background expiry check loop: {e}", exc_info=True)
            
        # Run check every 1 hour
        await asyncio.sleep(3600)

async def post_init(application: Application) -> None:
    asyncio.create_task(check_expired_licenses_loop(application))

async def admin(update, context):
    if update.effective_user.id != ADMIN_ID:
        return

    register_current_user(update)
    data = get_admin_stats()

    keyboard = [
        [
            InlineKeyboardButton("🔑 Gen Key", callback_data="admin_genkey_menu"),
            InlineKeyboardButton("👥 Users List", callback_data="admin_users"),
        ],
        [
            InlineKeyboardButton("💾 Backup DB", callback_data="admin_backup"),
            InlineKeyboardButton("📩 Latest Code", callback_data="admin_latest"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"🛠 Admin Dashboard\n\n"
        f"👥 Active Users: {data['users']}\n"
        f"🔑 Generated Keys: {data['keys']}\n"
        f"📩 Saved Codes: {data['codes']}",
        reply_markup=reply_markup
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
        "• /user USER_ID/@username - Get specific user info\n"
        "• /admin - View active stats overview\n\n"

        "📢 Communication:\n"
        "• /broadcast MESSAGE - Broadcast a message to all active users\n\n"

        "📊 Monitoring & History:\n"
        "• /license - View your own license info\n"
        "• /stats - View code repository stats\n"
        "• /history - View latest code history\n"
        "• /clearhistory - Clear saved verification codes\n"
        "• /backup - Download SQLite database backup\n\n"

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

    from telegram.error import RetryAfter
    sent = 0
    for user_id in users_list:
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=f"📢 Announcement\n\n{message}"
            )
            sent += 1
            await asyncio.sleep(0.05)  # Pause to avoid Telegram flood rate limits
        except RetryAfter as e:
            logger.warning(f"Rate limited. Sleeping for {e.retry_after} seconds.")
            await asyncio.sleep(e.retry_after)
            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=f"📢 Announcement\n\n{message}"
                )
                sent += 1
            except Exception as e_retry:
                logger.warning(f"Failed to broadcast to {user_id} after retry: {e_retry}")
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

    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()

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
    app.add_handler(CommandHandler("user", user_command))
    app.add_handler(CommandHandler("adminhelp", adminhelp))
    app.add_handler(CommandHandler("clearhistory", clearhistory))
    app.add_handler(CommandHandler("backup", backup))

    # Callback Query Handlers
    app.add_handler(CallbackQueryHandler(admin_callbacks))

    # Message handlers
    app.add_handler(MessageHandler(filters.Regex(r"^RAKEXURA-"), auto_activate))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, menu_buttons))

    logger.info("Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
