import os
import json
from flask import (
    Flask, render_template, request, redirect, url_for, session, flash, jsonify
)
from functools import wraps

# Optional: spreadsheet support
try:
    import gspread
    from google.oauth2.service_account import Credentials
    GSHEET_AVAILABLE = True
except Exception:
    GSHEET_AVAILABLE = False

# Basic config
app = Flask(__name__, static_folder="static", template_folder="templates")
app.secret_key = os.environ.get("SECRET_KEY", "replace_this_with_env_secret")

# Admin credentials (put secure values in Render env)
ADMIN_USER = os.environ.get("ADMIN_USER", "admin")
ADMIN_PASS = os.environ.get("ADMIN_PASS", "password123")

# Google sheet config
SHEET_ID = os.environ.get("SHEET_ID", "").strip()
# GOOGLE_CREDENTIALS should contain the JSON text of the service account key
GOOGLE_CREDENTIALS = os.environ.get("GOOGLE_CREDS_JSON", None)

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("admin_logged_in"):
            return redirect(url_for("admin_login", next=request.path))
        return f(*args, **kwargs)
    return decorated

def get_gspread_client():
    if not GSHEET_AVAILABLE:
        return None

    scopes = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
    creds = None

    if GOOGLE_CREDENTIALS:
        try:
            info = json.loads(GOOGLE_CREDENTIALS)
            creds = Credentials.from_service_account_info(info, scopes=scopes)
        except Exception as e:
            app.logger.warning("Failed to load GOOGLE_CREDENTIALS from env: %s", e)
            creds = None

    if creds is None and os.path.exists("credentials.json"):
        try:
            creds = Credentials.from_service_account_file("credentials.json", scopes=scopes)
        except Exception as e:
            app.logger.warning("Failed to load credentials.json: %s", e)
            creds = None

    if creds is None:
        return None

    try:
        client = gspread.authorize(creds)
        return client
    except Exception as e:
        app.logger.error("gspread.authorize error: %s", e)
        return None

def get_prices():
    client = get_gspread_client()
    if client is None:
        return None, "Google Sheets client unavailable. Check credentials."

    if not SHEET_ID:
        return None, "SHEET_ID not set in environment."

    try:
        sheet = client.open_by_key(SHEET_ID).worksheet("Prices")
        records = sheet.get_all_records()
        return records, None
    except Exception as e:
        app.logger.exception("Error fetching Prices sheet:")
        return None, f"Could not read Prices sheet: {e}"

def get_transactions():
    client = get_gspread_client()
    if client is None:
        return [], "Google Sheets client unavailable."
    if not SHEET_ID:
        return [], "SHEET_ID not set."
    try:
        sheet = client.open_by_key(SHEET_ID).worksheet("Transactions")
        records = sheet.get_all_records()
        return records, None
    except Exception as e:
        app.logger.exception("Error fetching Transactions sheet:")
        return [], f"Could not read Transactions sheet: {e}"

# ------------------- ROUTES -------------------

# Home / Index
@app.route("/")
def index():
    return render_template("index.html")

# Employee login / dashboard
@app.route("/employee", methods=["GET", "POST"])
def employee():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        # simple validation: replace with real creds
        if username == "employee" and password == "password":
            session["employee_logged_in"] = True
            return redirect(url_for("employee_dashboard"))
        else:
            flash("Invalid employee credentials", "danger")
            return redirect(url_for("employee"))

    return render_template("employee_login.html")

@app.route("/employee/dashboard")
def employee_dashboard():
    if not session.get("employee_logged_in"):
        return redirect(url_for("employee"))
    transactions, err = get_transactions()
    return render_template("employee.html", transactions=transactions, error=err)

@app.route("/employee/payout")
def employee_payout():
    if not session.get("employee_logged_in"):
        return redirect(url_for("employee"))
    transactions, err = get_transactions()
    return render_template("payout.html", transactions=transactions, error=err)

@app.route("/employee/receipt/<int:id>")
def employee_receipt(id):
    if not session.get("employee_logged_in"):
        return redirect(url_for("employee"))
    transactions, err = get_transactions()
    receipt = next((t for t in transactions if t.get("id") == id), None)
    if not receipt:
        return "Receipt not found", 404
    return render_template("receipt.html", receipt=receipt)

# Admin login / dashboard
@app.route("/admin", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        user = request.form.get("username", "")
        pwd = request.form.get("password", "")
        if user == ADMIN_USER and pwd == ADMIN_PASS:
            session["admin_logged_in"] = True
            flash("Welcome to Admin.", "success")
            next_url = request.args.get("next") or url_for("admin_dashboard")
            return redirect(next_url)
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
    return render_template("admin_dashboard.html")

@app.route("/admin/prices")
@login_required
def admin_prices():
    prices, err = get_prices()
    if err:
        return render_template("admin_prices.html", prices=[], error=err)
    return render_template("admin_prices.html", prices=prices, error=None)

@app.route("/admin/transactions")
@login_required
def admin_transactions():
    transactions, err = get_transactions()
    if err:
        return render_template("admin_transactions.html", transactions=[], error=err)
    return render_template("admin_transactions.html", transactions=transactions, error=None)

# Healthcheck
@app.route("/_health")
def health():
    return jsonify({"status": "ok"})

# Error handlers
@app.errorhandler(500)
def server_error(e):
    return render_template("500.html", error=e), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(host="0.0.0.0", port=port, debug=debug)
