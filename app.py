import os
import json
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from functools import wraps

# Optional: spreadsheet support
try:
    import gspread
    from google.oauth2.service_account import Credentials
    GSHEET_AVAILABLE = True
except Exception:
    GSHEET_AVAILABLE = False

# ----------------------
# App setup
# ----------------------
app = Flask(__name__, template_folder="templates", static_folder="static")
app.secret_key = os.environ.get("SECRET_KEY", "Passw0rd@123")

# Admin credentials
ADMIN_USER = os.environ.get("ADMIN_USER", "admin")
ADMIN_PASS = os.environ.get("ADMIN_PASS", "password123")

# Google Sheets config
SHEET_NAME = "RecycleWebApp"  # your sheet
GOOGLE_CREDENTIALS = os.environ.get("GOOGLE_CREDS_JSON", None)

# ----------------------
# Helpers
# ----------------------
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("admin_logged_in"):
            return redirect(url_for("admin_login"))
        return f(*args, **kwargs)
    return decorated

def get_gspread_client():
    if not GSHEET_AVAILABLE:
        return None
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = None
    if GOOGLE_CREDENTIALS:
        try:
            info = json.loads(GOOGLE_CREDENTIALS)
            creds = Credentials.from_service_account_info(info, scopes=scopes)
        except Exception as e:
            app.logger.warning("Failed to load GOOGLE_CREDENTIALS: %s", e)
    if creds is None and os.path.exists("credentials.json"):
        try:
            creds = Credentials.from_service_account_file("credentials.json", scopes=scopes)
        except Exception as e:
            app.logger.warning("Failed to load credentials.json: %s", e)
    if creds is None:
        return None
    try:
        client = gspread.authorize(creds)
        return client
    except Exception as e:
        app.logger.error("gspread authorize error: %s", e)
        return None

def get_transactions_sheet():
    client = get_gspread_client()
    if client is None:
        return None
    try:
        sheet = client.open(SHEET_NAME).worksheet("Transactions")
        return sheet
    except Exception as e:
        app.logger.error("Error opening Transactions sheet: %s", e)
        return None

def get_prices_sheet():
    client = get_gspread_client()
    if client is None:
        return None
    try:
        sheet = client.open(SHEET_NAME).worksheet("Prices")
        return sheet
    except Exception as e:
        app.logger.error("Error opening Prices sheet: %s", e)
        return None

# ----------------------
# Routes
# ----------------------
@app.route("/")
def index():
    return render_template("index.html")

# ----------------------
# Employee
# ----------------------
@app.route("/employee", methods=["GET", "POST"])
def employee():
    if request.method == "POST":
        session["employee_name"] = request.form.get("employee_name")
        if not session["employee_name"]:
            flash("Enter a name to continue.", "danger")
            return redirect(url_for("employee"))
        return redirect(url_for("payout"))
    return render_template("employee.html", employee_name=session.get("employee_name"))

@app.route("/employee/payout", methods=["GET", "POST"])
def payout():
    employee_name = session.get("employee_name")
    if not employee_name:
        return redirect(url_for("employee"))

    prices_sheet = get_prices_sheet()
    prices = []
    if prices_sheet:
        prices = prices_sheet.get_all_records()  # list of dicts: {"Material":..., "Price":...}

    if request.method == "POST":
        # collect submitted materials and amounts
        materials = []
        for i, price_row in enumerate(prices):
            mat = price_row["Material"]
            amount = request.form.get(f"amount_{i}", "")
            if amount:
                materials.append({
                    "material": mat,
                    "weight": amount,
                    "cost": float(amount) * float(price_row["Price"])
                })

        # save to Transactions sheet
        trans_sheet = get_transactions_sheet()
        if trans_sheet:
            for mat in materials:
                trans_sheet.append_row([
                    employee_name, mat["material"], mat["weight"], mat["cost"]
                ])
        # store in session to display in receipt
        session["last_receipt"] = materials
        return redirect(url_for("receipt"))

    return render_template("payout.html", employee_name=employee_name, prices=prices)

@app.route("/employee/receipt")
def receipt():
    materials = session.get("last_receipt", [])
    employee_name = session.get("employee_name", "Unknown")
    return render_template("receipt.html", materials=materials, employee_name=employee_name)

# ----------------------
# Admin
# ----------------------
@app.route("/admin", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        user = request.form.get("username")
        pwd = request.form.get("password")
        if user == ADMIN_USER and pwd == ADMIN_PASS:
            session["admin_logged_in"] = True
            return redirect(url_for("admin_dashboard"))
        else:
            flash("Invalid credentials.", "danger")
            return redirect(url_for("admin_login"))
    return render_template("admin_login.html")

@app.route("/admin/logout")
def admin_logout():
    session.pop("admin_logged_in", None)
    flash("Logged out.", "info")
    return redirect(url_for("admin_login"))

@app.route("/admin/dashboard")
@login_required
def admin_dashboard():
    # show today's transactions
    trans_sheet = get_transactions_sheet()
    transactions = []
    if trans_sheet:
        transactions = trans_sheet.get_all_records()
    return render_template("admin_dashboard.html", transactions=transactions)

@app.route("/admin/prices", methods=["GET", "POST"])
@login_required
def admin_prices():
    prices_sheet = get_prices_sheet()
    prices = []
    if prices_sheet:
        prices = prices_sheet.get_all_records()
    if request.method == "POST":
        # update prices
        for i, row in enumerate(prices):
            new_price = request.form.get(f"price_{i}")
            if new_price:
                prices_sheet.update_cell(i+2, 2, new_price)  # assuming header in row 1
        flash("Prices updated!", "success")
        return redirect(url_for("admin_prices"))
    return render_template("admin_prices.html", prices=prices)

# ----------------------
# Error handler
# ----------------------
@app.errorhandler(500)
def server_error(e):
    return render_template("500.html", error=e), 500

# ----------------------
# Healthcheck
# ----------------------
@app.route("/_health")
def health():
    return jsonify({"status": "ok"})

# ----------------------
# Run
# ----------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(host="0.0.0.0", port=port, debug=debug)
