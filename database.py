import sqlite3
import random
import string
from datetime import datetime, timedelta

def init_db():
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS codes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT NOT NULL
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS licenses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        license_key TEXT UNIQUE,
        days INTEGER,
        used INTEGER DEFAULT 0,
        used_by INTEGER,
        expiry TEXT
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        first_name TEXT,
        username TEXT,
        last_seen TEXT
    )
    """)

    conn.commit()
    conn.close()

def save_user_info(user_id, first_name, username):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO users (user_id, first_name, username, last_seen)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            first_name = excluded.first_name,
            username = excluded.username,
            last_seen = excluded.last_seen
        """,
        (user_id, first_name, username, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    )
    conn.commit()
    conn.close()

def get_license_expiry(user_id):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT expiry
        FROM licenses
        WHERE used_by = ? AND expiry IS NOT NULL
        ORDER BY expiry DESC
        LIMIT 1
        """,
        (user_id,)
    )

    row = cursor.fetchone()
    conn.close()

    return row[0] if row else None

def get_days_remaining(user_id):
    expiry = get_license_expiry(user_id)

    if not expiry:
        return None

    try:
        expiry_date = datetime.strptime(expiry, "%Y-%m-%d").date()
        today = datetime.now().date()
        days = (expiry_date - today).days
        return max(0, days)
    except ValueError:
        return 0

def generate_license(days):
    key = "RAKEXURA-" + ''.join(
        random.choices(
            string.ascii_uppercase + string.digits,
            k=8
        )
    )

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO licenses
        (license_key, days)
        VALUES (?, ?)
        """,
        (key, days)
    )

    conn.commit()
    conn.close()

    return key

def activate_license(key, user_id):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT days, used
        FROM licenses
        WHERE license_key = ?
        """,
        (key,)
    )

    row = cursor.fetchone()

    if not row:
        conn.close()
        return "invalid"

    days, used = row

    if used:
        conn.close()
        return "used"

    # Check if user already has an active license to stack/extend from
    cursor.execute(
        """
        SELECT expiry
        FROM licenses
        WHERE used_by = ? AND expiry IS NOT NULL
        ORDER BY expiry DESC
        LIMIT 1
        """,
        (user_id,)
    )
    active_row = cursor.fetchone()

    base_date = datetime.now()
    if active_row:
        try:
            current_expiry = datetime.strptime(active_row[0], "%Y-%m-%d")
            if current_expiry.date() >= datetime.now().date():
                base_date = current_expiry
        except ValueError:
            pass

    expiry = (base_date + timedelta(days=days)).strftime("%Y-%m-%d")

    cursor.execute(
        """
        UPDATE licenses
        SET used = 1,
            used_by = ?,
            expiry = ?
        WHERE license_key = ?
        """,
        (user_id, expiry, key)
    )

    conn.commit()
    conn.close()

    return expiry

def is_user_active(user_id):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT expiry
        FROM licenses
        WHERE used_by = ? AND expiry IS NOT NULL
        ORDER BY expiry DESC
        LIMIT 1
        """,
        (user_id,)
    )

    row = cursor.fetchone()
    conn.close()

    if not row:
        return False

    try:
        expiry_date = datetime.strptime(row[0], "%Y-%m-%d").date()
        return expiry_date >= datetime.now().date()
    except ValueError:
        return False

def save_code(code):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    cursor.execute(
        "INSERT INTO codes (code) VALUES (?)",
        (code,)
    )

    conn.commit()
    conn.close()

def clear_history():
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    cursor.execute("DELETE FROM codes")

    conn.commit()
    conn.close()

def code_exists(code):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    cursor.execute(
        "SELECT 1 FROM codes WHERE code=?",
        (code,)
    )

    result = cursor.fetchone()
    conn.close()

    return result is not None

def get_history(limit=5):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    cursor.execute(
        "SELECT code FROM codes ORDER BY id DESC LIMIT ?",
        (limit,)
    )

    rows = cursor.fetchall()
    conn.close()

    return [row[0] for row in rows]

def get_stats():
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM codes")
    total = cursor.fetchone()[0]

    cursor.execute(
        "SELECT code FROM codes ORDER BY id DESC LIMIT 1"
    )

    latest = cursor.fetchone()
    conn.close()

    return {
        "total": total,
        "latest": latest[0] if latest else "None"
    }

def get_admin_stats():
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM licenses")
    total_keys = cursor.fetchone()[0]

    # Count unique users with at least one active license today
    today = datetime.now().strftime("%Y-%m-%d")
    cursor.execute(
        """
        SELECT COUNT(DISTINCT used_by)
        FROM licenses
        WHERE used = 1 AND used_by IS NOT NULL AND expiry >= ?
        """,
        (today,)
    )
    active_users = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM codes")
    total_codes = cursor.fetchone()[0]

    conn.close()

    return {
        "keys": total_keys,
        "users": active_users,
        "codes": total_codes
    }

def get_users():
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    # Get unique users, their latest expiry, and their name/username from the users table
    cursor.execute("""
        SELECT l.used_by, MAX(l.expiry) as latest_expiry, u.first_name, u.username
        FROM licenses l
        LEFT JOIN users u ON l.used_by = u.user_id
        WHERE l.used = 1 AND l.used_by IS NOT NULL
        GROUP BY l.used_by
    """)

    users = cursor.fetchall()
    conn.close()

    return users

def get_all_user_ids():
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    # Get all unique active users today
    today = datetime.now().strftime("%Y-%m-%d")
    cursor.execute("""
        SELECT DISTINCT used_by
        FROM licenses
        WHERE used = 1 AND used_by IS NOT NULL AND expiry >= ?
    """, (today,))

    users = cursor.fetchall()
    conn.close()

    return [user[0] for user in users if user[0] is not None]

def revoke_user(user_id):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    cursor.execute(
        """
        UPDATE licenses
        SET used = 0,
            used_by = NULL,
            expiry = NULL
        WHERE used_by = ?
        """,
        (user_id,)
    )

    conn.commit()
    conn.close()

def extend_license(user_id, days):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT id, expiry
        FROM licenses
        WHERE used_by = ? AND expiry IS NOT NULL
        ORDER BY expiry DESC
        LIMIT 1
        """,
        (user_id,)
    )

    row = cursor.fetchone()

    if not row:
        conn.close()
        return False

    license_id, expiry = row

    try:
        expiry_dt = datetime.strptime(expiry, "%Y-%m-%d")
    except ValueError:
        conn.close()
        return False

    new_expiry = (expiry_dt + timedelta(days=days)).strftime("%Y-%m-%d")

    cursor.execute(
        """
        UPDATE licenses
        SET expiry = ?
        WHERE id = ?
        """,
        (new_expiry, license_id)
    )

    conn.commit()
    conn.close()

    return new_expiry