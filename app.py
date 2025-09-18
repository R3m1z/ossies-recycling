# app.py
import os
import os
import json
from google.oauth2 import service_account
from googleapiclient.discovery import build

# Load Google Sheets credentials from environment variable
creds_dict = json.loads(os.environ['GOOGLE_CREDS_JSON'])
credentials = service_account.Credentials.from_service_account_info(creds_dict)
service = build('sheets', 'v4', credentials=credentials)
SHEET_ID = "1g6LBASqzygH2KFWdik4aj2iSJfr_jNibK0GOm4geYN4"  # replace with your spreadsheet ID
ADMIN_USER = "admin"
ADMIN_PASS = "Admin@123"
SECRET_KEY = "dev-secret"

# ---------- Flask ----------
app = Flask(__name__)
app.secret_key = SECRET_KEY

# ---------- Google Sheets ----------
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
credentials = service_account.Credentials.from_service_account_file(
    SERVICE_ACCOUNT_FILE, scopes=SCOPES)
sheets_service = build('sheets', 'v4', credentials=credentials)

def get_prices():
    """Return list of (material, unit_price)"""
    result = sheets_service.spreadsheets().values().get(
        spreadsheetId=SHEET_ID,
        range='Prices!A2:B'
    ).execute()
    values = result.get('values', [])
    prices = []
    for row in values:
        name = row[0]
        price = float(row[1]) if len(row) > 1 else 0.0
        prices.append((name, price))
    return prices

def append_transactions(rows):
    """Append transaction rows to Transactions sheet"""
    body = {"values": rows}
    sheets_service.spreadsheets().values().append(
        spreadsheetId=SHEET_ID,
        range='Transactions!A1:G1',
        valueInputOption='USER_ENTERED',
        insertDataOption='INSERT_ROWS',
        body=body
    ).execute()

def update_prices_batch(price_rows):
    """Batch overwrite Prices sheet"""
    rows = [["Material", "UnitPrice"]] + [[m, str(p)] for m, p in price_rows]
    body = {
        "valueInputOption": "USER_ENTERED",
        "data": [
            {
                "range": f"Prices!A1:B{len(rows)}",
                "majorDimension": "ROWS",
                "values": rows
            }
        ]
    }
    sheets_service.spreadsheets().values().batchUpdate(
        spreadsheetId=SHEET_ID,
        body=body
    ).execute()

# ---------- Routes ----------
@app.route('/')
def home():
    return render_template('home.html')

@app.route('/employee', methods=['GET', 'POST'])
def employee():
    if request.method == 'POST':
        name = request.form.get('employee_name', '').strip()
        if not name:
            flash("Enter your name")
            return redirect(url_for('employee'))
        return redirect(url_for('payout', employee=name))
    return render_template('employee_login.html')

@app.route('/payout', methods=['GET', 'POST'])
def payout():
    employee = request.args.get('employee') or request.form.get('employee')
    prices = get_prices()
    if request.method == 'POST':
        txn_id = uuid.uuid4().hex[:8]
        timestamp = datetime.utcnow().isoformat()
        receipt_items = []
        total = 0.0
        rows_to_append = []
        for mat, price in prices:
            weight_str = request.form.get(f"weights[{mat}]","0")
            try:
                weight = float(weight_str)
            except:
                weight = 0.0
            cost = round(weight*price,2)
            if weight > 0:
                rows_to_append.append([timestamp, employee, txn_id, mat, weight, price, cost])
                receipt_items.append({'mat':mat,'weight':weight,'price':price,'cost':cost})
                total += cost
        if not rows_to_append:
            flash("Enter at least one weight")
            return redirect(url_for('payout', employee=employee))
        append_transactions(rows_to_append)
        return render_template('receipt.html', items=receipt_items, total=total, employee=employee, txn_id=txn_id)
    return render_template('payout.html', employee=employee, prices=prices)

@app.route('/admin', methods=['GET','POST'])
def admin_login():
    if request.method == 'POST':
        user = request.form.get('username')
        pw = request.form.get('password')
        if user == ADMIN_USER and pw == ADMIN_PASS:
            session['is_admin'] = True
            return redirect(url_for('admin_dashboard'))
        flash("Invalid credentials")
    return render_template('admin_login.html')

def admin_required(f):
    from functools import wraps
    @wraps(f)
    def wrap(*args, **kwargs):
        if not session.get('is_admin'):
            flash("Login required")
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return wrap

@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    return render_template('admin_dashboard.html')

@app.route('/admin/transactions')
@admin_required
def admin_transactions():
    result = sheets_service.spreadsheets().values().get(
        spreadsheetId=SHEET_ID,
        range='Transactions!A1:G'
    ).execute()
    rows = result.get('values', [])
    headers = rows[0] if rows else []
    data = rows[1:] if len(rows)>1 else []
    return render_template('admin_transactions.html', headers=headers, rows=data)

@app.route('/admin/prices', methods=['GET','POST'])
@admin_required
def admin_prices():
    if request.method == 'POST':
        mats = request.form.getlist('material')
        units = request.form.getlist('unitprice')
        price_rows = []
        for m,p in zip(mats, units):
            try: pval=float(p)
            except: pval=0.0
            if m.strip():
                price_rows.append((m.strip(), pval))
        update_prices_batch(price_rows)
        flash("Prices updated")
        return redirect(url_for('admin_prices'))
    prices = get_prices()
    return render_template('admin_prices.html', prices=prices)

@app.route('/admin/logout')
def admin_logout():
    session.pop('is_admin', None)
    flash("Logged out")
    return redirect(url_for('home'))

# ---------- run ----------
if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))

