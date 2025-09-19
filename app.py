import os
import json
from flask import Flask, render_template, request, redirect, url_for, session, flash
from functools import wraps

# Google Sheets support
import gspread
from google.oauth2.service_account import Credentials

app = Flask(__name__, template_folder="templates")
app.secret_key = os.environ.get("SECRET_KEY", "replace_this_with_env_secret")

# Admin credentials
ADMIN_USER = os.environ.get("ADMIN_USER", "admin")
ADMIN_PASS = os.environ.get("ADMIN_PASS", "password123")

# Google Sheets config
SHEET_ID = os.environ.get("SHEET_ID", "")
GOOGLE_CREDS_JSON = os.environ.get("GOOGLE_CREDS_JSON", "")

# ----------- Google Sheets helper ------------
def get_gspread_client():
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = Credentials.from_service_account_info(json.loads(GOOGLE_CREDS_JSON), scopes=scopes)
    return gspread.authorize(creds)

def get_materials():
    """Returns a dict of {material_name: price} from 'Prices' sheet"""
    try:
        client = get_gspread_client()
        sheet = client.open_by_key(SHEET_ID).worksheet("Prices")
        records = sheet.get_all_records()
        materials = {row["Material"]: row["Price"] for row in records}
        return materials
    except Exception as e:
        app.logger.error(f"Error fetching materials: {e}")
        return {}

# ----------- Decorators ------------
def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("admin_logged_in"):
            return redirect(url_for("admin_login"))
        return f(*args, **kwargs)
    return wrapper

# ----------- Routes ------------

@app.route("/")
def index():
    return render_template("index.html")

# ----- Employee Flow -----
@app.route("/employee", methods=["GET", "POST"])
def employee_home():
    if request.method == "POST":
        name = request.form.get("employee_name", "").strip()
        if not name:
            flash("Please enter your name", "danger")
            return redirect(url_for("employee_home"))
        session["employee_name"] = name
        return redirect(url_for("employee_payout"))
    return render_template("employee_home.html")

@app.route("/employee/payout", methods=["GET", "POST"])
def employee_payout():
    employee_name = session.get("employee_name")
    if not employee_name:
        return redirect(url_for("employee_home"))

    materials = get_materials()

    if request.method == "POST":
        weights = request.form.get("weights")
        if not weights:
            flash("Please enter weights", "danger")
            return redirect(url_for("employee_payout"))
        # Store submitted weights in session for receipt
        session["weights"] = request.form.getlist("weights")
        # Transform into dict
        weight_dict = {k: float(v or 0) for k, v in request.form.get("weights", {}).items()}
        session["weight_dict"] = weight_dict
        return redirect(url_for("receipt"))

    return render_template("employee_payout.html", employee_name=employee_name, materials=materials)

@app.route("/employee/receipt")
def receipt():
    employee_name = session.get("employee_name")
    weight_dict = session.get("weight_dict", {})
    materials = get_materials()
    receipt_items = []
    total = 0
    for mat, weight in weight_dict.items():
        price = materials.get(mat, 0)
        amount = price * weight
        receipt_items.append({"material": mat, "weight": weight, "price": price, "amount": amount})
        total += amount
    return render_template("receipt.html", employee_name=employee_name, items=receipt_items, total=total)

# ----- Admin Flow -----
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
    # TODO: Load today's transactions from Google Sheets
    return render_template("admin_dashboard.html")

@app.route("/admin/prices", methods=["GET", "POST"])
@admin_required
def admin_prices():
    materials = get_materials()
    if request.method == "POST":
        # update Google Sheets prices
        client = get_gspread_client()
        sheet = client.open_by_key(SHEET_ID).worksheet("Prices")
        for i, material in enumerate(materials.keys(), start=2):
            new_price = request.form.get(material)
            if new_price:
                sheet.update(f"B{i}", float(new_price))
        flash("Prices updated!", "success")
        return redirect(url_for("admin_prices"))
    return render_template("admin_prices.html", materials=materials)

@app.route("/admin/transactions")
@admin_required
def admin_transactions():
    # TODO: load transactions from Google Sheets
    return render_template("admin_transactions.html")

# -------- Error Handling ---------
@app.errorhandler(500)
def server_error(e):
    return render_template("500.html", error=e), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
