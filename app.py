import os
import io
import base64
import requests
import sqlite3
import random
from flask import Flask, render_template, request, session, redirect, url_for, jsonify, flash
from datetime import datetime, timedelta
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)

# --- 🔐 SECURITY & CONFIG ---
app.secret_key = os.environ.get('SECRET_KEY', 'AgriGuard_SLU_2026_Alpha')
app.permanent_session_lifetime = timedelta(minutes=60)

# Paths (Using /tmp/ for Render compatibility)
DB_PATH = '/tmp/agriguard.db'

# --- 🗄️ DATABASE CORE ---
def init_db():
    try:
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        conn = sqlite3.connect(DB_PATH)
        conn.execute('''CREATE TABLE IF NOT EXISTS users 
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                     username TEXT UNIQUE, email TEXT, password TEXT)''')
        conn.execute('''CREATE TABLE IF NOT EXISTS scans 
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                     user TEXT, crop TEXT, status TEXT, time TEXT)''')
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Database Error: {e}")

init_db()

# --- 🔐 AUTH MIDDLEWARE ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# --- 🚀 ROUTES ---

@app.route('/')
@login_required
def index():
    # Variables required by your index.html
    lang = request.args.get('lang', 'en')
    weather_data = {'city': 'Kampala', 'temp': '28', 'desc': 'Partly Cloudy'}
    t_content = {'title': 'Agri-Guard Intelligence'}
    
    return render_template('index.html', 
                           current_lang=lang, 
                           weather=weather_data, 
                           t=t_content)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = request.form.get('username')
        pw = request.form.get('password')
        try:
            conn = sqlite3.connect(DB_PATH)
            row = conn.execute("SELECT password FROM users WHERE username = ?", (user,)).fetchone()
            conn.close()
            if row and check_password_hash(row[0], pw):
                session['logged_in'] = True
                session['username'] = user
                return redirect(url_for('index'))
            flash("Invalid Credentials", "error")
        except Exception as e:
            return f"Login Error: {str(e)}"
    return render_template('login.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        user = request.form.get('username')
        email = request.form.get('email')
        pw = generate_password_hash(request.form.get('password'))
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.execute("INSERT INTO users (username, email, password) VALUES (?, ?, ?)", (user, email, pw))
            conn.commit()
            conn.close()
            return redirect(url_for('login'))
        except:
            flash("User already exists", "error")
    return render_template('signup.html')

@app.route('/predict', methods=['POST'])
@login_required
def predict():
    file = request.files.get('file')
    if not file: return redirect(url_for('index'))
    
    # Mock AI logic for defense demo
    crop, conf, status = "Maize (Mahindi)", 94.2, "HEALTHY"
    advice = "Neural analysis indicates optimal chlorophyll levels. No pathogens detected."
    prescription = "Continue current irrigation schedule and monitor for Fall Armyworm sightings in the area."
    
    # Image processing for display
    img_bytes = file.read()
    encoded_img = base64.b64encode(img_bytes).decode('utf-8')
    user_image = f"data:image/jpeg;base64,{encoded_img}"

    return render_template('index.html', 
                           prediction=f"{crop} ({conf}%)", 
                           advice=advice, 
                           prescription=prescription,
                           user_image=user_image,
                           current_lang=request.form.get('lang', 'en'),
                           weather={'city': 'Kampala', 'temp': '28', 'desc': 'Partly Cloudy'},
                           t={'title': 'Agri-Guard Intelligence'})

@app.route('/analytics_data')
@login_required
def analytics_data():
    # Feeds the Chart.js doughnut chart
    return jsonify({
        "labels": ["Healthy", "Blight", "Mosaic", "Rust"],
        "values": [70, 10, 15, 5]
    })

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
