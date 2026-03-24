import os
import io
import base64
import requests
import sqlite3
import numpy as np
from flask import Flask, render_template, request, session, redirect, url_for, jsonify, flash
from datetime import datetime, timedelta
from functools import wraps
from PIL import Image
from werkzeug.security import generate_password_hash, check_password_hash

# --- 🧠 AI ENGINE SETUP ---
# Optimized for Render: We don't load the heavy model until the app is fully live
LOCAL_MODEL = None
LOCAL_AI_READY = False

def load_local_ai():
    global LOCAL_MODEL, LOCAL_AI_READY
    if LOCAL_MODEL is None:
        try:
            import tensorflow as tf
            # Using MobileNetV2 as a lightweight local buffer
            LOCAL_MODEL = tf.keras.applications.MobileNetV2(weights='imagenet')
            LOCAL_AI_READY = True
        except Exception as e:
            print(f"Local AI Buffer disabled: {e}")
            LOCAL_AI_READY = False

app = Flask(__name__)

# --- 🔐 SECURITY CONFIG ---
# Pulls the key you just set in Render. Fallback is for local testing.
app.secret_key = os.environ.get('SECRET_KEY', 'AgriGuard_SLU_2026_Alpha')
app.permanent_session_lifetime = timedelta(minutes=60)

# Paths - Using /tmp/ is mandatory for Render's Free Tier
DB_PATH = '/tmp/agriguard.db'
UPLOAD_FOLDER = os.path.join('static', 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# API Configuration
PLANT_ID_API_KEY = os.getenv("PLANT_ID_API_KEY")
OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY")

# --- 🗄️ DATABASE CORE ---
def init_db():
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute('''CREATE TABLE IF NOT EXISTS users 
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                      username TEXT UNIQUE, 
                      email TEXT, 
                      password TEXT)''')
        conn.execute('''CREATE TABLE IF NOT EXISTS scans 
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                      user TEXT, crop TEXT, status TEXT, time TEXT)''')
        conn.commit()
        conn.close()
        print("✅ Database initialized successfully.")
    except Exception as e:
        print(f"❌ Database Error: {e}")

# --- 🔐 SECURITY MIDDLEWARE ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# --- 🛠️ AI UTILITIES ---
def analyze_plant(image_bytes):
    """Hybrid Cloud Diagnosis with Plant.id"""
    if not PLANT_ID_API_KEY: return "Demo Crop", 95, "HEALTHY"
    
    encoded = base64.b64encode(image_bytes).decode('ascii')
    payload = {
        "images": [encoded],
        "latitude": 0.3476, "longitude": 32.5825, # Kampala Coordinates
        "modifiers": ["crops_fast", "disease_all"]
    }
    headers = {"Api-Key": PLANT_ID_API_KEY}
    
    try:
        res = requests.post("https://api.plant.id/v2/identify", json=payload, headers=headers, timeout=15)
        data = res.json()
        sug = data['suggestions'][0]
        health = data.get('health_assessment', {}).get('is_healthy', True)
        return sug['plant_name'].title(), round(sug['probability']*100, 1), "HEALTHY" if health else "DISEASE DETECTED"
    except:
        return "Unknown Crop", 0, "SCAN ERROR"

def get_llama_advice(crop, status):
    """AI Prescription via OpenRouter (Llama 3)"""
    if not OPENROUTER_KEY: return "Ensure proper drying and store in PICS bags."
    
    prompt = f"Provide 3 organic treatment steps for {crop} in Uganda with {status}. Focus on Aflatoxin safety."
    try:
        res = requests.post("https://openrouter.ai/api/v1/chat/completions", 
            headers={"Authorization": f"Bearer {OPENROUTER_KEY}"},
            json={"model": "meta-llama/llama-3.1-8b-instruct:free", "messages": [{"role": "user", "content": prompt}]})
        return res.json()['choices'][0]['message']['content']
    except:
        return "Maintain moisture below 13% for safe storage."

# --- 🚀 SYSTEM ROUTES ---

@app.route('/')
@login_required
def index():
    return render_template('index.html', 
                           t={'title': 'Agri-Guard Intelligence'},
                           weather={'city': 'Kampala', 'temp': '27', 'desc': 'Sunny'})

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = request.form.get('username')
        pw = request.form.get('password')
        conn = sqlite3.connect(DB_PATH)
        row = conn.execute("SELECT password FROM users WHERE username = ?", (user,)).fetchone()
        conn.close()
        
        if row and check_password_hash(row[0], pw):
            session.permanent = True
            session['logged_in'] = True
            session['username'] = user
            return redirect(url_for('index'))
        flash("Invalid Credentials", "error")
    return render_template('login.html')

@app.route('/signup', methods=['POST'])
def signup():
    user = request.form.get('username')
    email = request.form.get('email')
    pw = generate_password_hash(request.form.get('password'))
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute("INSERT INTO users (username, email, password) VALUES (?, ?, ?)", (user, email, pw))
        conn.commit()
        conn.close()
        flash("Registration Successful! Please Login.", "success")
    except:
        flash("Username already exists.", "error")
    return redirect(url_for('login'))

@app.route('/predict', methods=['POST'])
@login_required
def predict():
    file = request.files.get('file')
    if not file: return redirect(url_for('index'))
    
    img_bytes = file.read()
    crop, conf, status = analyze_plant(img_bytes)
    advice = get_llama_advice(crop, status)
    
    return render_template('index.html', 
                           prediction=f"{crop} ({conf}%)", 
                           advice=f"STATUS: {status}", 
                           prescription=advice,
                           t={'title': 'Agri-Guard Intelligence'},
                           weather={'city': 'Kampala', 'temp': '27', 'desc': 'Sunny'})

@app.route('/analytics_data')
@login_required
def analytics_data():
    return jsonify({"labels": ["Healthy", "Molds", "Nutrient Deficient"], "values": [65, 20, 15]})

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# --- 🏁 EXECUTION ---
if __name__ == '__main__':
    # Initialize DB inside app context to ensure Render reliability
    with app.app_context():
        init_db()
    
    # Grab the dynamic PORT from Render, default to 5000 for local dev
    port = int(os.environ.get("PORT", 5000))
    # host='0.0.0.0' is CRITICAL for public visibility on Render
    app.run(host='0.0.0.0', port=port, debug=False)
