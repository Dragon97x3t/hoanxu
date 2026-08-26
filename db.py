"""
Lớp truy cập cơ sở dữ liệu (SQLite) cho Hoàn Xu.
Không dùng ORM để giữ code đơn giản, dễ đọc cho người không rành lập trình.
"""
import sqlite3
import os
import secrets
import string
from datetime import datetime, timezone
from werkzeug.security import generate_password_hash

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hoanxu.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    ref_code TEXT NOT NULL UNIQUE,
    is_admin INTEGER NOT NULL DEFAULT 0,
    bank_info TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    sub_id TEXT NOT NULL,
    shopee_order_id TEXT,
    product_name TEXT,
    order_amount REAL NOT NULL DEFAULT 0,
    commission_amount REAL NOT NULL DEFAULT 0,
    cashback_amount REAL NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'pending', -- pending | confirmed | rejected
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    import_batch TEXT,
    FOREIGN KEY(user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS withdrawals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    amount REAL NOT NULL,
    bank_info TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'requested', -- requested | paid | rejected
    created_at TEXT NOT NULL,
    processed_at TEXT,
    FOREIGN KEY(user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS clicks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ref_code TEXT NOT NULL,
    target_url TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

DEFAULT_SETTINGS = {
    # % hoa hồng chia lại cho người dùng (phần còn lại là doanh thu của chủ site)
    "cashback_share_percent": "70",
    # Mẫu link affiliate Shopee - ADMIN CẦN THAY BẰNG LINK THẬT CỦA MÌNH.
    # {sub_id} sẽ được thay bằng mã giới thiệu của người dùng, {target_url} là link sản phẩm Shopee.
    "shopee_link_template": "https://REPLACE-WITH-YOUR-SHOPEE-AFFILIATE-LINK?subid={sub_id}&url={target_url}",
}


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def gen_ref_code(length=7):
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def init_db():
    first_time = not os.path.exists(DB_PATH)
    conn = get_db()
    conn.executescript(SCHEMA)

    for k, v in DEFAULT_SETTINGS.items():
        conn.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v)
        )

    # Tạo tài khoản admin mặc định nếu chưa có admin nào
    admin = conn.execute("SELECT id FROM users WHERE is_admin = 1").fetchone()
    if admin is None:
        ref = gen_ref_code()
        conn.execute(
            """INSERT INTO users (name, email, password_hash, ref_code, is_admin, created_at)
               VALUES (?, ?, ?, ?, 1, ?)""",
            (
                "Quản trị viên",
                "admin@hoanxu.local",
                generate_password_hash("admin123"),
                ref,
                now_iso(),
            ),
        )
        conn.commit()
        print("=" * 60)
        print("Đã tạo tài khoản admin mặc định:")
        print("  Email: admin@hoanxu.local")
        print("  Mật khẩu: admin123")
        print("  -> Hãy đăng nhập và đổi mật khẩu ngay.")
        print("=" * 60)

    conn.commit()
    conn.close()
    return first_time


def get_setting(conn, key, default=None):
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(conn, key, value):
    conn.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
    conn.commit()
