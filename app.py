# app.py
from flask import Flask, render_template, request, redirect, url_for, flash
import os
import json
from googleapiclient.discovery import build
from google.oauth2 import service_account

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'supersecretkey')

# Google Sheets setup
SHEET_ID = os.environ.get('SHEET_ID')  # Your Google Sheet ID
creds_json = os.environ.get('GOOGLE_CREDS_JSON')
if not creds_json:
    raise ValueError("Set the GOOGLE_CREDS_JSON environment variable")

credentials = service_account.Credentials.from_service_account_info(json.loads(creds_json))
service = build('sheets', 'v4', credentials=credentials)

# Helper functions
def get_prices():
    sheet = service.spreadsheets()
    result = sheet.values().get(spreadsheetId=SHEET_ID, range='Prices!A2:B').execute()
    values = result.get('values', [])
    return [(row[0], float(row[1])) for row in values if len(row) == 2]

def update_prices(prices_list):
    # prices_list = [('Material1', 10), ('Material2', 20)]
    sheet = service.spreadsheets()
    sheet.values().update(
        spreadsheetId=SHEET_ID,
        range='Prices!A2:B',
        valueInputOption='USER_ENTERED',
        body={'values': prices_list}
    ).execute()

def get_transactions():
    sheet = service.spreadsheets()
    result = sheet.values().get(spreadsheetId=SHEET_ID, range='Transactions!A2:E').execute()
    return result.get('values', [])

def add_transaction(employee, materials):
    sheet = service.spreadsheets()
    sheet.values().append(
        spreadsheetId=SHEET_ID,
        range='Transactions!A2:E',
        valueInputOption='USER_ENTERED',
        body={'values': [[employee] + materials]}
    ).execute()

# Routes
@app.route('/')
def home():
    return render_template('home.html')

# Employee login
@app.route('/employee', methods=['GET', 'POST'])
def employee():
    if request.method == 'POST':
        employee_name = request.form.get('employee')
        if not employee_name:
            flash("Please enter your name")
            return redirect(url_for('employee'))
        return redirect(url_for('payout', employee=employee_name))
    return render_template('employee.html')

@app.route('/payout', methods=['GET', 'POST'])
def payout():
    employee = request.args.get('employee')
    prices = get_prices()
    if request.method == 'POST':
        # Example: materials = [weight1, weight2,...]
        materials = request.form.getlist('weight')
        # Add transaction to sheet
        add_transaction(employee, materials)
        flash("Transaction recorded!")
        return redirect(url_for('payout', employee=employee))
    return render_template('payout.html', employee=employee, prices=prices)

# Admin login
@app.route('/admin', methods=['GET', 'POST'])
def admin():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        if username == os.environ.get('ADMIN_USER') and password == os.environ.get('ADMIN_PASS'):
            return redirect(url_for('admin_dashboard'))
        flash("Invalid credentials")
    return render_template('admin.html')

@app.route('/admin/dashboard')
def admin_dashboard():
    return render_template('admin_dashboard.html')

@app.route('/admin/prices', methods=['GET', 'POST'])
def admin_prices():
    prices = get_prices()
    if request.method == 'POST':
        # Example: request.form = {'Material1': '10', 'Material2': '20'}
        updated = [(k, float(v)) for k, v in request.form.items()]
        update_prices(updated)
        flash("Prices updated!")
        return redirect(url_for('admin_prices'))
    return render_template('admin_prices.html', prices=prices)

@app.route('/admin/transactions')
def admin_transactions():
    transactions = get_transactions()
    return render_template('admin_transactions.html', transactions=transactions)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))

