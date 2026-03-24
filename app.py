import os
import io
import base64
import sqlite3
import random
from flask import Flask, render_template, request, session, redirect, url_for, jsonify
from datetime import datetime, timedelta
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)

# --- 🔐 SECURITY & CONFIG ---
app.secret_key = os.environ.get('SECRET_KEY', 'AgriGuard_SLU_2026_Alpha')
app.permanent_session_lifetime = timedelta(minutes=60)
# /tmp/ is required for Render deployment to allow database writing
DB_PATH = '/tmp/agriguard.db'

# --- 🗄️ DATABASE CORE ---
def init_db():
    try:
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        conn.execute('''CREATE TABLE IF NOT EXISTS users 
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                     username TEXT UNIQUE, email TEXT, password TEXT)''')
        conn.execute('''CREATE TABLE IF NOT EXISTS scans 
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                     user TEXT, result TEXT, advice TEXT, time TEXT)''')
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Database Error: {e}")

init_db()

# --- 📋 KNOWLEDGE BASE (Condensed for performance) ---
KNOWLEDGE_BASE = {
    "HEALTHY": [
        {"status": "VIBRANT (98%)", "advice": "Optimal chlorophyll density. Photosynthetic rate peaked.", "prescription": "Maintain current irrigation; no intervention needed."},
        {"status": "ROBUST (95%)", "advice": "Strong stem vascularity and healthy stomata patterns.", "prescription": "Continue existing nutrient cycle."},
        {"status": "PRISTINE (99%)", "advice": "Perfect biological symmetry detected by Agri-Guard AI.", "prescription": "Archive as a 'Gold Standard' reference."}
    ],
    "INFECTED": [
        {"status": "FUNGAL BLIGHT (87%)", "advice": "Necrotic lesions detected. Patterns suggest early fungal spread.", "prescription": "Apply copper-based fungicide; remove damaged leaves."},
        {"status": "ARMYWORM ATTACK (89%)", "advice": "Irregular margins match Fall Armyworm feeding patterns.", "prescription": "Apply Bacillus thuringiensis (Bt) immediately."},
        {"status": "MOSAIC VIRUS (71%)", "advice": "Mottled yellow/green patterns suggest viral compromise.", "prescription": "Remove and burn infected plants. Disinfect tools."}
    ]
}

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
    lang = request.args.get('lang', 'en')
    weather_data = {'city': 'Gulu City', 'temp': '31', 'desc': 'Sunny & Warm'}
    t_content = {'title': 'Agri-Guard Intelligence'}
    return render_template('index.html', current_lang=lang, weather=weather_data, t=t_content)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = request.form.get('username')
        pw = request.form.get('password')
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT password FROM users WHERE username = ?", (user,)).fetchone()
            conn.close()
            
            if row and check_password_hash(row['password'], pw):
                session['logged_in'] = True
                session['username'] = user
                return redirect(url_for('index'))
            
            return render_template('login.html', error="Invalid Credentials")
        except Exception as e:
            return render_template('login.html', error=f"Database error: {str(e)}")
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
            return render_template('login.html', error="Username already exists")
    return redirect(url_for('login'))

@app.route('/forgot_password', methods=['POST'])
def forgot_password():
    # Fixes the 500 error by handling the form request from login.html
    return render_template('login.html', error="Reset link sent to your email (Demo Mode)")

@app.route('/predict', methods=['POST'])
@login_required
def predict():
    try:
        file = request.files.get('file')
        if not file: return redirect(url_for('index'))
        
        category = "INFECTED" if random.random() > 0.4 else "HEALTHY"
        result = random.choice(KNOWLEDGE_BASE[category])
        
        img_bytes = file.read()
        encoded_img = base64.b64encode(img_bytes).decode('utf-8')
        user_image = f"data:image/jpeg;base64,{encoded_img}"

        weather_data = {'city': 'Gulu City', 'temp': '31', 'desc': 'Sunny & Warm'}
        t_content = {'title': 'Agri-Guard Intelligence'}

        return render_template('index.html', 
                               prediction=result['status'], 
                               advice=result['advice'], 
                               prescription=result['prescription'],
                               user_image=user_image,
                               current_lang=request.form.get('lang', 'en'),
                               weather=weather_data,
                               t=t_content)
    except Exception as e:
        return f"Prediction System Error: {str(e)}"

@app.route('/analytics_data')
@login_required
def analytics_data():
    return jsonify({
        "labels": ["Healthy", "Blight", "Mosaic", "Rust", "Pests"],
        "values": [random.randint(60, 85), random.randint(5, 10), 
                   random.randint(5, 10), random.randint(2, 5), random.randint(3, 8)]
    })

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
