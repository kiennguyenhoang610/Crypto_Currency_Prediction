from flask import Flask, render_template, url_for, request, redirect, session
from datetime import datetime
import os
import TreePredict
import time # Used to simulate execution time for the Retrain feature

app = Flask(__name__)
# Mandatory security key to use Login feature (session)
app.secret_key = 'super_secret_key_hcmut'

# -----------------------------------------
# MOCK DATABASE: Mock database for Stakeholders
# -----------------------------------------
MOCK_USERS = {
    "admin": {"password": "123", "role": "admin"},
    "kien": {"password": "123", "role": "user"},
    "scientist": {"password": "123", "role": "scientist"}
}

stock_name = ""
day_name = ""

# =========================================
# 1. LOGIN & AUTHENTICATION MODULE
# =========================================
@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        role = request.form['role'] # NEW: Capture Role information submitted from the form

        # NEW: Validate all 3 elements: Username, Password, AND Role
        if username in MOCK_USERS and MOCK_USERS[username]['password'] == password and MOCK_USERS[username]['role'] == role:
            # Login successful
            session['role'] = MOCK_USERS[username]['role']
            session['username'] = username
            
            # Redirect based on Role
            if session['role'] == 'admin':
                return redirect('/admin_dashboard')
            elif session['role'] == 'scientist':
                return redirect('/scientist_dashboard')
            else:
                return redirect('/') # Regular user
        else:
            # Generic error message to increase security (do not reveal if it's wrong password or wrong role)
            error = "Invalid username, password, or role!"
            
    return render_template('login.html', error=error)

@app.route('/logout')
def logout():
    session.clear() # Clear session data
    return redirect(url_for('login'))


# =========================================
# 2. END-USER MODULE
# =========================================
@app.route('/', methods=['POST', 'GET'])
def home():
    # Only allow access if logged in (Optional security)
    if 'role' not in session:
        return redirect('/login')

    if request.method == "POST":
        stock_name = request.form['stock_type']
        day_name = request.form['next_day']
        print("Received request for:", stock_name)
        return render_template('user.html')
    else:
        return render_template('user.html')

@app.route('/predict/', methods=['POST'])
def predict():
    # Get information from Form
    stock_type = request.form.get('stock_type', 'BTC')
    next_time_str = request.form.get('next_time', '1')
    model_choice = request.form.get('model_choice', 'both')
    
    # Convert next_time to integer
    try:
        days = int(next_time_str)
    except:
        days = 1

    # Call AI function with dynamic parameters
    tree_result, rf_result = TreePredict.PredictValue(stock_type, days)

    # Auto-generate labels for the chart
    # labels_1: Last 6 days
    labels_1 = ["T-5", "T-4", "T-3", "T-2", "T-1", "Today"]
    # labels_2: Last 6 days + Target day
    labels_2 = labels_1 + [f"Day +{days}"]

    return render_template('test.html',
                           labels_1=labels_1, 
                           data_1=tree_result[:6].tolist(), # Get only the past 6 days
                           labels_2=labels_2, 
                           data_2=tree_result.tolist(), 
                           data_rf=rf_result.tolist(),
                           CurrentValue="{:,.2f}".format(tree_result[5]), 
                           PredictValue_DT="{:,.2f}".format(tree_result[6]), 
                           PredictValue_RF="{:,.2f}".format(rf_result[6]),
                           model_choice=model_choice,
                           next_time=days)


# =========================================
# 3. ADMIN MODULE
# =========================================
@app.route('/admin_dashboard')
def admin_dashboard():
    # Check permissions: Only admin can access admin.html
    if 'role' in session and session['role'] == 'admin':
        return render_template('admin.html')
    return redirect('/login')


# =========================================
# 4. DATA SCIENTIST MODULE
# =========================================
@app.route('/scientist_dashboard')
def scientist_dashboard():
    if 'role' in session and session['role'] == 'scientist':
        metrics = {
            "dt_rmse": "1,245.50", # RMSE error of Decision Tree
            "dt_mae": "980.20",    # MAE error of Decision Tree
            "rf_rmse": "850.75",   # Random Forest has lower error -> Better performance
            "rf_mae": "610.30",
            "last_trained": "07/04/2026"
        }
        return render_template('scientist.html', metrics=metrics)
    return redirect('/login')

@app.route('/retrain', methods=['POST'])
def retrain_model():
    if 'role' in session and session['role'] == 'scientist':
        time.sleep(2) # Simulate system taking 2 seconds to crawl data and retrain
        return "The process of crawling new data and retraining models was successful!"
    return redirect('/login')


# Run the Flask app
if __name__ == "__main__":
    app.run(debug=True)