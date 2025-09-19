import os
import json
import uuid
from datetime import datetime, date
from functools import wraps

from flask import Flask, render_template, request, redirect, url_for, session, flash
import gspread
from google.oauth2.service_account import Credentials

# ---------- App config ----------
app = Flask(__name__, template_folder="templates")
app.secret_key = os.environ.get("SECRET_KEY", "Passw0rd@123")

ADMIN_USER = os.environ.get("ADMIN_USER", "admin")
ADMIN_PASS = os.environ.get("ADMIN_PASS", "password123")

SHEET_ID = os.environ.get("SHEET_ID", "").strip()
GOOGLE_CREDS_JSON = os.environ.get("GOOGLE_CREDS_JSON", "").strip()

PRICES_SHEET_NAME = "Prices"
PRICES_HEADERS = ["Material", "Price"]

TRANSACTIONS_SHEET_NAME = "Transactions"
TRANSACTIONS_HEADERS = ["TransactionID","Date", "Employee", "Material", "Weight", "Price", "Amount"]

# ---------- Google Sheets helpers ----------
def sheets_enabled():
    return bool(SHEET_ID and GOOGLE_CREDS_JSON)

def get_gspread_client():
    if not sheets_enabled():
        raise RuntimeError("Google Sheets not configured (SHEET_ID or GOOGLE_CREDS_JSON missing).")
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds_info = json.loads(GOOGLE_CREDS_JSON)
    creds = Credentials.from_service_account_info(creds_info, scopes=scopes)
    return gspread.authorize(creds)

def ensure_worksheet(sheet_name, headers):
    client = get_gspread_client()
    sh = client.open_by_key(SHEET_ID)
    try:
        ws = sh.worksheet(sheet_name)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=sheet_name, rows=1000, cols=len(headers)+3)
        ws.append_row(headers)
    return ws

def get_materials():
    try:
        ws = ensure_worksheet(PRICES_SHEET_NAME, PRICES_HEADERS)
        records = ws.get_all_records()
        materials = {}
        for r in records:
            name = r.get("Material")
            price = r.get("Price", 0)
            try:
                materials[name] = float(price)
            except:
                materials[name] = 0.0
        return materials
    except Exception as e:
        app.logger.error("get_materials error: %s", e)
        return {}

def save_prices(prices_dict):
    try:
        ws = ensure_worksheet(PRICES_SHEET_NAME, PRICES_HEADERS)
        ws.clear()
        ws.append_row(PRICES_HEADERS)
        for mat, price in prices_dict.items():
            ws.append_row([mat, float(price)])
        return True, None
    except Exception as e:
        app.logger.exception("save_prices error")
        return False, str(e)

def append_transactions(employee_name, weight_dict):
    try:
        ws = ensure_worksheet(TRANSACTIONS_SHEET_NAME, TRANSACTIONS_HEADERS)
        materials = get_materials()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        transaction_id = str(uuid.uuid4())[:8]  # short unique ID
        rows = []
        for mat, weight in weight_dict.items():
            try:
                w = float(weight)
            except:
                w = 0.0
            if w <= 0:
                continue  # skip zero weights
            price = float(materials.get(mat, 0.0))
            amount = round(price * w, 2)
            rows.append([transaction_id, now, employee_name, mat, w, price, amount])
        for r in rows:
            ws.append_row(r)
        return transaction_id, None
    except Exception as e:
        app.logger.exception("append_transactions error")
        return None, str(e)

def get_transactions(all_rows=True):
    try:
        ws = ensure_worksheet(TRANSACTIONS_SHEET_NAME, TRANSACTIONS_HEADERS)
        records = ws.get_all_records()
        if not all_rows:
            today_prefix = date.today().strftime("%Y-%m-%d")
            records = [r for r in records if str(r.get("Date", "")).startswith(today_prefix)]
        return records, None
    except Exception as e:
        app.logger.exception("get_transactions error")
        return [], str(e)

# ---------- Decorators ----------
def admin_required(route):
    @wraps(route)
    def wrapper(*args, **kwargs):
        if not session.get("admin_logged_in"):
            return redirect(url_for("admin_login"))
        return route(*args, **kwargs)
    return wrapper

def employee_required(route):
    @wraps(route)
    def wrapper(*args, **kwargs):
        if not session.get("employee_name"):
            return redirect(url_for("employee_login"))
        return route(*args, **kwargs)
    return wrapper

# ---------- Routes ----------
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/home")
def home():
    return render_template("home.html")

# -------- Employee flow --------
@app.route("/employee/login", methods=["GET", "POST"])
def employee_login():
    if request.method == "POST":
        name = request.form.get("employee_name", "").strip()
        if not name:
            flash("Please enter your name to continue.", "danger")
            return redirect(url_for("employee_login"))
        session["employee_name"] = name
        session.pop("weight_dict", None)
        session.pop("transaction_id", None)
        return redirect(url_for("employee_payout"))
    return render_template("employee_login.html")

@app.route("/employee/payout", methods=["GET", "POST"])
@employee_required
def employee_payout():
    employee_name = session.get("employee_name")
    materials = get_materials()

    if request.method == "POST":
        weight_dict = {}
        for mat in materials.keys():
            raw = request.form.get(mat, "").strip()
            weight = float(raw) if raw else 0.0
            weight_dict[mat] = weight

        session["weight_dict"] = weight_dict
        transaction_id, err = append_transactions(employee_name, weight_dict)
        if err:
            flash(f"Warning: transaction not saved to sheet: {err}", "danger")
        else:
            flash("Transaction saved.", "success")
            session["transaction_id"] = transaction_id

        return redirect(url_for("employee_receipt"))

    return render_template("employee_payout.html", employee_name=employee_name, materials=materials)

@app.route("/employee/receipt")
@employee_required
def employee_receipt():
    employee_name = session.get("employee_name")
    weight_dict = session.get("weight_dict", {}) or {}
    prices = get_materials()
    transaction_id = session.get("transaction_id", "")

    materials_for_receipt = {}
    total = 0.0
    for mat, weight in weight_dict.items():
        price = float(prices.get(mat, 0.0))
        if weight > 0:
            amount = round(weight * price, 2)
            materials_for_receipt[mat] = {'weight': weight, 'price': amount}
            total += amount
    total = round(total, 2)

    return render_template(
        "receipt.html",
        client_name=employee_name,
        date=datetime.now().strftime("%Y-%m-%d %H:%M"),
        transaction_id=transaction_id,
        materials=materials_for_receipt,
        total=total
    )

# -------- Admin flow --------
@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        user = request.form.get("username", "")
        pwd = request.form.get("password", "")
        if user == ADMIN_USER and pwd == ADMIN_PASS:
            session["admin_logged_in"] = True
            flash("Welcome, admin.", "success")
            return redirect(url_for("admin_dashboard"))
        flash("Invalid credentials.", "danger")
        return redirect(url_for("admin_login"))
    return render_template("admin_login.html")

@app.route("/admin/logout")
def admin_logout():
    session.pop("admin_logged_in", None)
    flash("Logged out.", "info")
    return redirect(url_for("admin_login"))

@app.route("/admin/dashboard")
@admin_required
def admin_dashboard():
    transactions = []
    err = None
    if sheets_enabled():
        transactions, err = get_transactions(all_rows=False)
        if err:
            flash(f"Could not load transactions: {err}", "danger")
    else:
        flash("Google Sheets not configured — admin views are limited.", "warning")
    return render_template("admin_dashboard.html", transactions=transactions)

@app.route("/admin/prices", methods=["GET", "POST"])
@admin_required
def admin_prices():
    materials = get_materials()
    if request.method == "POST":
        new_prices = {}
        for mat in materials.keys():
            raw = request.form.get(mat, "").strip()
            if raw == "":
                continue
            try:
                new_prices[mat] = float(raw)
            except:
                flash(f"Invalid price for {mat}.", "danger")
                return redirect(url_for("admin_prices"))
        merged = dict(materials)
        merged.update(new_prices)
        ok, err = save_prices(merged)
        if not ok:
            flash(f"Error saving prices: {err}", "danger")
        else:
            flash("Prices updated.", "success")
        return redirect(url_for("admin_prices"))
    return render_template("admin_prices.html", materials=materials)

@app.route("/admin/transactions")
@admin_required
def admin_transactions():
    transactions = []
    err = None
    if sheets_enabled():
        transactions, err = get_transactions(all_rows=True)
        if err:
            flash(f"Could not load transactions: {err}", "danger")
    else:
        flash("Google Sheets not configured — transactions unavailable.", "warning")
    return render_template("admin_transactions.html", transactions=transactions)

# ---------- Error handlers ----------
@app.errorhandler(500)
def server_error(e):
    return render_template("500.html", error=e), 500

# ---------- Run ----------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
