"""
Hoàn Xu - lõi ứng dụng (MVP)
Chạy: python3 app.py
Xem README.md để biết hướng dẫn đầy đủ.
"""
import csv
import io
import os
import secrets
from datetime import datetime, timezone
from functools import wraps
from urllib.parse import quote

from flask import (
    Flask, render_template, request, redirect, url_for, session, flash, abort
)
from werkzeug.security import generate_password_hash, check_password_hash

import db

def _load_or_create_secret_key():
    """Lấy SECRET_KEY từ biến môi trường, hoặc tạo và lưu vào file cục bộ.

    Quan trọng: không dùng secrets.token_hex() trực tiếp làm secret_key mỗi lần
    khởi động, vì khi chạy production với nhiều worker process (gunicorn -w),
    mỗi worker sẽ có key khác nhau và làm hỏng phiên đăng nhập (session) của
    người dùng một cách ngẫu nhiên. Trên Render, nên đặt biến môi trường
    SECRET_KEY thật để ổn định qua các lần deploy lại.
    """
    env_key = os.environ.get("SECRET_KEY")
    if env_key:
        return env_key
    key_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".secret_key")
    if os.path.exists(key_path):
        with open(key_path, "r") as f:
            return f.read().strip()
    new_key = secrets.token_hex(32)
    with open(key_path, "w") as f:
        f.write(new_key)
    return new_key


app = Flask(__name__)
app.secret_key = _load_or_create_secret_key()
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

# Khởi tạo database ngay khi module được nạp, để chạy đúng cả khi dùng
# `python3 app.py` (dev) lẫn khi chạy qua gunicorn (production trên Render...).
db.init_db()


# ---------------------------------------------------------------------------
# Tiện ích chung
# ---------------------------------------------------------------------------

def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("login"))
        if not session.get("is_admin"):
            abort(403)
        return view(*args, **kwargs)
    return wrapped


def current_user(conn):
    uid = session.get("user_id")
    if not uid:
        return None
    return conn.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()


def wallet_summary(conn, user_id):
    pending = conn.execute(
        "SELECT COALESCE(SUM(cashback_amount),0) s FROM orders WHERE user_id=? AND status='pending'",
        (user_id,),
    ).fetchone()["s"]
    confirmed = conn.execute(
        "SELECT COALESCE(SUM(cashback_amount),0) s FROM orders WHERE user_id=? AND status='confirmed'",
        (user_id,),
    ).fetchone()["s"]
    withdrawn_paid = conn.execute(
        "SELECT COALESCE(SUM(amount),0) s FROM withdrawals WHERE user_id=? AND status='paid'",
        (user_id,),
    ).fetchone()["s"]
    withdrawn_requested = conn.execute(
        "SELECT COALESCE(SUM(amount),0) s FROM withdrawals WHERE user_id=? AND status='requested'",
        (user_id,),
    ).fetchone()["s"]
    available = confirmed - withdrawn_paid - withdrawn_requested
    return {
        "pending": pending,
        "confirmed": confirmed,
        "withdrawn_paid": withdrawn_paid,
        "withdrawn_requested": withdrawn_requested,
        "available": max(available, 0),
    }


@app.context_processor
def inject_globals():
    return {"app_name": "Hoàn Xu"}


# ---------------------------------------------------------------------------
# Xác thực
# ---------------------------------------------------------------------------

def _mask_name(name):
    name = (name or "Người dùng").strip()
    if len(name) <= 2:
        return name[0] + "***"
    return name[:2] + "***"


@app.route("/")
def index():
    if session.get("user_id"):
        return redirect(url_for("dashboard"))

    conn = db.get_db()
    stats = {
        "total_confirmed": conn.execute(
            "SELECT COALESCE(SUM(cashback_amount),0) s FROM orders WHERE status IN ('confirmed')"
        ).fetchone()["s"],
        "total_orders": conn.execute(
            "SELECT COUNT(*) c FROM orders WHERE status IN ('confirmed','pending')"
        ).fetchone()["c"],
        "total_users": conn.execute("SELECT COUNT(*) c FROM users WHERE is_admin=0").fetchone()["c"],
    }
    recent = conn.execute(
        """SELECT o.product_name, o.cashback_amount, o.status, o.created_at, u.name
           FROM orders o JOIN users u ON u.id = o.user_id
           ORDER BY o.created_at DESC LIMIT 6"""
    ).fetchall()
    activity = [
        {
            "who": _mask_name(r["name"]),
            "product": r["product_name"] or "một đơn hàng",
            "amount": r["cashback_amount"],
            "status": r["status"],
        }
        for r in recent
    ]
    conn.close()
    return render_template("home.html", stats=stats, activity=activity)


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not name or not email or len(password) < 6:
            flash("Vui lòng nhập đủ họ tên, email và mật khẩu (ít nhất 6 ký tự).", "error")
            return render_template("register.html")

        conn = db.get_db()
        exists = conn.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()
        if exists:
            conn.close()
            flash("Email này đã được đăng ký. Hãy đăng nhập.", "error")
            return render_template("register.html")

        ref = db.gen_ref_code()
        while conn.execute("SELECT id FROM users WHERE ref_code=?", (ref,)).fetchone():
            ref = db.gen_ref_code()

        conn.execute(
            "INSERT INTO users (name, email, password_hash, ref_code, created_at) VALUES (?,?,?,?,?)",
            (name, email, generate_password_hash(password), ref, db.now_iso()),
        )
        conn.commit()
        user = conn.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        conn.close()

        session["user_id"] = user["id"]
        session["is_admin"] = bool(user["is_admin"])
        flash("Tạo ví thành công! Đây là link giới thiệu của bạn.", "success")
        return redirect(url_for("dashboard"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        conn = db.get_db()
        user = conn.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        conn.close()
        if user and check_password_hash(user["password_hash"], password):
            session["user_id"] = user["id"]
            session["is_admin"] = bool(user["is_admin"])
            return redirect(request.args.get("next") or url_for("dashboard"))
        flash("Email hoặc mật khẩu không đúng.", "error")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ---------------------------------------------------------------------------
# Bảng điều khiển người dùng
# ---------------------------------------------------------------------------

@app.route("/dashboard")
@login_required
def dashboard():
    conn = db.get_db()
    user = current_user(conn)
    wallet = wallet_summary(conn, user["id"])
    orders = conn.execute(
        "SELECT * FROM orders WHERE user_id=? ORDER BY created_at DESC LIMIT 50",
        (user["id"],),
    ).fetchall()
    withdrawals = conn.execute(
        "SELECT * FROM withdrawals WHERE user_id=? ORDER BY created_at DESC LIMIT 20",
        (user["id"],),
    ).fetchall()
    ref_link = url_for("go", ref_code=user["ref_code"], _external=True)
    conn.close()
    return render_template(
        "dashboard.html", user=user, wallet=wallet, orders=orders,
        withdrawals=withdrawals, ref_link=ref_link,
    )


@app.route("/withdraw", methods=["GET", "POST"])
@login_required
def withdraw():
    conn = db.get_db()
    user = current_user(conn)
    wallet = wallet_summary(conn, user["id"])

    if request.method == "POST":
        try:
            amount = float(request.form.get("amount", "0").replace(",", ""))
        except ValueError:
            amount = 0
        bank_info = request.form.get("bank_info", "").strip()

        if amount <= 0 or amount > wallet["available"]:
            flash("Số tiền yêu cầu rút không hợp lệ (vượt quá số dư khả dụng).", "error")
        elif not bank_info:
            flash("Vui lòng nhập thông tin ngân hàng nhận tiền.", "error")
        else:
            conn.execute(
                "INSERT INTO withdrawals (user_id, amount, bank_info, status, created_at) "
                "VALUES (?,?,?,'requested',?)",
                (user["id"], amount, bank_info, db.now_iso()),
            )
            conn.execute("UPDATE users SET bank_info=? WHERE id=?", (bank_info, user["id"]))
            conn.commit()
            flash("Đã gửi yêu cầu rút tiền. Admin sẽ xử lý trong thời gian sớm nhất.", "success")
            conn.close()
            return redirect(url_for("dashboard"))

    conn.close()
    return render_template("withdraw.html", user=user, wallet=wallet)


# ---------------------------------------------------------------------------
# Link giới thiệu / chuyển hướng affiliate
# ---------------------------------------------------------------------------

@app.route("/go/<ref_code>")
def go(ref_code):
    conn = db.get_db()
    user = conn.execute("SELECT * FROM users WHERE ref_code=?", (ref_code,)).fetchone()
    if not user:
        conn.close()
        abort(404)

    target_url = request.args.get("url", "").strip()
    conn.execute(
        "INSERT INTO clicks (ref_code, target_url, created_at) VALUES (?,?,?)",
        (ref_code, target_url, db.now_iso()),
    )
    conn.commit()

    template = db.get_setting(conn, "shopee_link_template")
    conn.close()

    final_url = template.format(sub_id=quote(ref_code), target_url=quote(target_url, safe=""))
    return redirect(final_url)


# ---------------------------------------------------------------------------
# Khu vực quản trị (admin)
# ---------------------------------------------------------------------------

CSV_EXPECTED_COLUMNS = ["sub_id", "shopee_order_id", "product_name", "order_amount", "commission_amount", "status"]
STATUS_MAP = {
    "pending": "pending", "unpaid": "pending", "chờ xác nhận": "pending",
    "confirmed": "confirmed", "completed": "confirmed", "đã xác nhận": "confirmed", "hoàn thành": "confirmed",
    "rejected": "rejected", "cancelled": "rejected", "invalid": "rejected", "đã huỷ": "rejected", "không hợp lệ": "rejected",
}


@app.route("/admin")
@admin_required
def admin_home():
    conn = db.get_db()
    stats = {
        "users": conn.execute("SELECT COUNT(*) c FROM users").fetchone()["c"],
        "pending_cashback": conn.execute(
            "SELECT COALESCE(SUM(cashback_amount),0) s FROM orders WHERE status='pending'"
        ).fetchone()["s"],
        "confirmed_cashback": conn.execute(
            "SELECT COALESCE(SUM(cashback_amount),0) s FROM orders WHERE status='confirmed'"
        ).fetchone()["s"],
        "paid_out": conn.execute(
            "SELECT COALESCE(SUM(amount),0) s FROM withdrawals WHERE status='paid'"
        ).fetchone()["s"],
    }
    pending_withdrawals = conn.execute(
        "SELECT w.*, u.name, u.email FROM withdrawals w JOIN users u ON u.id=w.user_id "
        "WHERE w.status='requested' ORDER BY w.created_at ASC"
    ).fetchall()
    users = conn.execute("SELECT * FROM users ORDER BY created_at DESC").fetchall()
    conn.close()
    return render_template("admin_home.html", stats=stats, pending_withdrawals=pending_withdrawals, users=users)


@app.route("/admin/withdrawals/<int:wid>/<action>", methods=["POST"])
@admin_required
def admin_withdrawal_action(wid, action):
    if action not in ("paid", "rejected"):
        abort(400)
    conn = db.get_db()
    conn.execute(
        "UPDATE withdrawals SET status=?, processed_at=? WHERE id=?",
        (action, db.now_iso(), wid),
    )
    conn.commit()
    conn.close()
    flash("Đã cập nhật yêu cầu rút tiền.", "success")
    return redirect(url_for("admin_home"))


@app.route("/admin/import", methods=["GET", "POST"])
@admin_required
def admin_import():
    preview = None
    if request.method == "POST":
        file = request.files.get("csv_file")
        if not file or file.filename == "":
            flash("Vui lòng chọn một file CSV.", "error")
            return render_template("admin_import.html", preview=None, expected=CSV_EXPECTED_COLUMNS)

        content = file.stream.read().decode("utf-8-sig", errors="replace")
        reader = csv.DictReader(io.StringIO(content))
        conn = db.get_db()
        share_pct = float(db.get_setting(conn, "cashback_share_percent", "70"))

        batch = db.now_iso()
        matched, unmatched, updated = 0, 0, 0

        for row in reader:
            row = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
            sub_id = row.get("sub_id", "")
            user = conn.execute("SELECT id FROM users WHERE ref_code=?", (sub_id,)).fetchone()
            if not user:
                unmatched += 1
                continue

            raw_status = row.get("status", "pending").strip().lower()
            status = STATUS_MAP.get(raw_status, "pending")

            try:
                commission = float((row.get("commission_amount") or "0").replace(",", ""))
            except ValueError:
                commission = 0
            try:
                order_amount = float((row.get("order_amount") or "0").replace(",", ""))
            except ValueError:
                order_amount = 0

            cashback = round(commission * share_pct / 100, 0)
            shopee_order_id = row.get("shopee_order_id", "")

            existing = None
            if shopee_order_id:
                existing = conn.execute(
                    "SELECT id FROM orders WHERE shopee_order_id=? AND user_id=?",
                    (shopee_order_id, user["id"]),
                ).fetchone()

            if existing:
                conn.execute(
                    "UPDATE orders SET status=?, commission_amount=?, cashback_amount=?, "
                    "order_amount=?, product_name=?, updated_at=?, import_batch=? WHERE id=?",
                    (status, commission, cashback, order_amount, row.get("product_name", ""),
                     db.now_iso(), batch, existing["id"]),
                )
                updated += 1
            else:
                conn.execute(
                    "INSERT INTO orders (user_id, sub_id, shopee_order_id, product_name, order_amount, "
                    "commission_amount, cashback_amount, status, created_at, updated_at, import_batch) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (user["id"], sub_id, shopee_order_id, row.get("product_name", ""), order_amount,
                     commission, cashback, status, db.now_iso(), db.now_iso(), batch),
                )
                matched += 1

        conn.commit()
        conn.close()
        flash(f"Nhập xong: {matched} đơn mới, {updated} đơn cập nhật, {unmatched} dòng không khớp mã giới thiệu.", "success")
        return redirect(url_for("admin_import"))

    return render_template("admin_import.html", preview=preview, expected=CSV_EXPECTED_COLUMNS)


@app.route("/admin/settings", methods=["GET", "POST"])
@admin_required
def admin_settings():
    conn = db.get_db()
    if request.method == "POST":
        pct = request.form.get("cashback_share_percent", "70")
        template = request.form.get("shopee_link_template", "").strip()
        db.set_setting(conn, "cashback_share_percent", pct)
        if template:
            db.set_setting(conn, "shopee_link_template", template)
        flash("Đã lưu cài đặt.", "success")
        return redirect(url_for("admin_settings"))

    settings = {
        "cashback_share_percent": db.get_setting(conn, "cashback_share_percent", "70"),
        "shopee_link_template": db.get_setting(conn, "shopee_link_template", ""),
    }
    conn.close()
    return render_template("admin_settings.html", settings=settings)


if __name__ == "__main__":
    db.init_db()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=os.environ.get("DEBUG") == "1")
