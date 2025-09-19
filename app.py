import os
import json
from flask import Flask, render_template, request, redirect, url_for, session, flash
from functools import wraps

# Google Sheets
import gspread
from google.oauth2.service_account import Credentials

app = Flask(__name__, template_folder="templates")
app.secret_key = os.environ.get("SECRET_KEY", "Passw0rd@123")

# Admin credentials
ADMIN_USER = os.environ.get("ADMIN_USER", "admin")
ADMIN_PASS = os.environ.get("ADMIN_PASS", "password123")

# Google Sheets
SHEET_ID = os.environ.get("SHEET_ID", "")
GOOGLE_CREDS_JSON = os.environ.get("GOOGLE_CREDS_JSON", "")

# ---------------- Google Sheets Helpers ----------------
def get_gspread_client():
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = Credentials.from_service_account_info(json.loads(GOOGLE_CREDS_JSON), scopes=scopes)
    return gspread.authorize(creds)

def get_materials():
    """Returns dict of {material_name: price} from Prices sheet"""
    try:
        client = get_gspread_client()
        sheet = client.open_by_key(SHEET_ID).worksheet("Prices")
        records = sheet.get_all_records()
        materials = {row["Material"]: float(row["Price"]) for row in records}
        return materials
    except Exception as e:
        app.logger.error(f"Error fetching materials: {e}")
        return {}

def save_transaction(employee, weights_dict):
    """Append transaction to Google Sheet 'Transactions'"""
    try:
        client = get_gspread_client()
        sheet = client.open_by_key(SHEET_ID).worksheet("Transactions")
        from datetime import datetime
        for mat, weight in weights_dict.items():
            sheet.append_row([datetime.now().strftime("%Y-%m-%d %H:%M"), employee, mat, weight])
    except Exception as e:
        app.logger.error(f"Error saving transaction: {e}")

# ---------------- Decorators ----------------
def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("admin_logged_in"):
            return redirect(url_for("admin_login"))
        return f(*args, **kwargs)
    return wrapper

# ---------------- Routes ----------------
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/home")
def home():
    return render_template("home.html")

# ---------------- Employee ----------------
@app.route("/employee", methods=["GET", "POST"])
def employee_login():
    if request.method == "POST":
        name = request.form.get("employee_name", "").strip()
        if not name:
            flash("Enter your name to continue", "danger")
            return redirect(url_for("employee_login"))
        session["employee_name"] = name
        return redirect(url_for("employee_payout"))
    return render_template("employee_login.html")

@app.route("/employee/payout", methods=["GET", "POST"])
def employee_payout():
    employee_name = session.get("employee_name")
    if not employee_name:
        return redirect(url_for("employee_login"))

    materials = get_materials()

    if request.method == "POST":
        # weights comes from form fields named after materials
        weights_dict = {}
        for mat in materials:
            val = request.form.get(mat, "0")
            try:
                weights_dict[mat] = float(val)
            except:
                weights_dict[mat] = 0
        session["weight_dict"] = weights_dict
        save_transaction(employee_name, weights_dict)
        return redirect(url_for("receipt"))

    return render_template("employee_payout.html", employee_name=employee_name, materials=materials)

@app.route("/employee/receipt")
def receipt():
    employee_name = session.get("employee_name")
    weight_dict = session.get("weight_dict", {})
    materials = get_materials()
    items = []
    total = 0
    for mat, weight in weight_dict.items():
        price = materials.get(mat, 0)
        amount = weight * price
        items.append({"material": mat, "weight": weight, "price": price, "amount": amount})
        total += amount
    return render_template("receipt.html", employee_name=employee_name, items=items, total=total)

# ---------------- Admin ----------------
@app.route("/admin", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        user = request.form.get("username")
        pwd = request.form.get("password")
        if user == ADMIN_USER and pwd == ADMIN_PASS:
            session["admin_logged_in"] = True
            return redirect(url_for("admin_dashboard"))
        flash("Invalid credentials", "danger")
    return render_template("admin_login.html")

@app.route("/admin/logout")
def admin_logout():
    session.pop("admin_logged_in", None)
    return redirect(url_for("admin_login"))

@app.route("/admin/dashboard")
@admin_required
def admin_dashboard():
    # Load today's transactions
    transactions = []
    try:
        client = get_gspread_client()
        sheet = client.open_by_key(SHEET_ID).worksheet("Transactions")
        records = sheet.get_all_records()
        transactions = records
    except Exception as e:
        flash(f"Error loading transactions: {e}", "danger")
    return render_template("admin_dashboard.html", transactions=transactions)

@app.route("/admin/prices", methods=["GET", "POST"])
@admin_required
def admin_prices():
    materials = get_materials()
    if request.method == "POST":
        try:
            client = get_gspread_client()
            sheet = client.open_by_key(SHEET_ID).worksheet("Prices")
            for i, mat in enumerate(materials.keys(), start=2):
                val = request.form.get(mat)
                if val:
                    sheet.update(f"B{i}", float(val))
            flash("Prices updated!", "success")
            return redirect(url_for("admin_prices"))
        except Exception as e:
            flash(f"Error updating prices: {e}", "danger")
    return render_template("admin_prices.html", materials=materials)

@app.route("/admin/transactions")
@admin_required
def admin_transactions():
    # List all transactions
    transactions = []
    try:
        client = get_gspread_client()
        sheet = client.open_by_key(SHEET_ID).worksheet("Transactions")
        transactions = sheet.get_all_records()
    except Exception as e:
        flash(f"Error loading transactions: {e}", "danger")
    return render_template("admin_transactions.html", transactions=transactions)

# ---------------- Error ----------------
@app.errorhandler(500)
def server_error(e):
    return render_template("500.html", error=e), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
