import os
from flask import Flask, render_template, request, redirect, url_for, flash, session
import gspread
from google.oauth2.service_account import Credentials

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "supersecretkey")  # Set a secure key in Render

# -----------------------------
# Google Sheets setup
# -----------------------------
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
SHEET_ID = os.environ.get("1g6LBASqzygH2KFWdik4aj2iSJfr_jNibK0GOm4geYN4")  # Set your sheet ID as an environment variable

# Load credentials safely from JSON file or env variable
def get_gs_client():
    creds_json = os.environ.get("GOOGLE_CREDS_JSON")
    if not creds_json:
        raise Exception("GOOGLE_CREDS_JSON environment variable not set")
    creds_dict = eval(creds_json)  # JSON string stored in env variable
    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    client = gspread.authorize(creds)
    return client

def get_prices():
    client = get_gs_client()
    sheet = client.open_by_key(SHEET_ID).worksheet("Prices")
    data = sheet.get_all_values()[1:]  # Skip header row
    return [(row[0], float(row[1])) for row in data]

def update_prices(prices_dict):
    client = get_gs_client()
    sheet = client.open_by_key(SHEET_ID).worksheet("Prices")
    all_data = sheet.get_all_values()
    for i, row in enumerate(all_data[1:], start=2):
        item = row[0]
        if item in prices_dict:
            sheet.update(f"B{i}", prices_dict[item])

def log_transaction(employee, items):
    client = get_gs_client()
    sheet = client.open_by_key(SHEET_ID).worksheet("Transactions")
    for mat, weight, cost in items:
        sheet.append_row([employee, mat, weight, cost])

# -----------------------------
# Routes
# -----------------------------

@app.route('/')
def home():
    return render_template("home.html")

# Employee login & payout
@app.route('/employee', methods=['GET', 'POST'])
def employee():
    if request.method == 'POST':
        employee_name = request.form.get('employee_name')
        session['employee'] = employee_name
        return redirect(url_for('payout'))
    return render_template("employee_select.html")

@app.route('/payout', methods=['GET', 'POST'])
def payout():
    prices = get_prices()
    if request.method == 'POST':
        items = []
        total_cost = 0
        for mat, price in prices:
            weight = float(request.form.get(mat, 0))
            cost = weight * price
            total_cost += cost
            items.append((mat, weight, cost))
        log_transaction(session.get('employee', 'Unknown'), items)
        return render_template("receipt.html", items=items, total=total_cost, employee=session.get('employee'))
    return render_template("payout.html", prices=prices)

# Admin login
@app.route('/admin', methods=['GET', 'POST'])
def admin():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        if username == os.environ.get("ADMIN_USER") and password == os.environ.get("ADMIN_PASS"):
            session['admin'] = True
            return redirect(url_for('admin_dashboard'))
        else:
            flash("Invalid credentials", "danger")
    return render_template("admin_login.html")

@app.route('/admin/dashboard')
def admin_dashboard():
    if not session.get('admin'):
        return redirect(url_for('admin'))
    return render_template("admin_dashboard.html")

@app.route('/admin/prices', methods=['GET', 'POST'])
def admin_prices():
    if not session.get('admin'):
        return redirect(url_for('admin'))
    prices = get_prices()
    if request.method == 'POST':
        new_prices = {k: float(v) for k, v in request.form.items()}
        update_prices(new_prices)
        flash("Prices updated successfully!", "success")
        return redirect(url_for('admin_prices'))
    return render_template("admin_prices.html", prices=prices)

@app.route('/admin/transactions')
def admin_transactions():
    if not session.get('admin'):
        return redirect(url_for('admin'))
    client = get_gs_client()
    sheet = client.open_by_key(SHEET_ID).worksheet("Transactions")
    transactions = sheet.get_all_values()[1:]
    return render_template("admin_transactions.html", transactions=transactions)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))

# -----------------------------
# Run app
# -----------------------------
if __name__ == '__main__':
    app.run(debug=True)

