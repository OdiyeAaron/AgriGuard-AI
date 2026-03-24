import os
import io
import base64
import requests
import sqlite3
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

# API Keys (Ensure these are set in Render -> Environment)
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
    except Exception as e:
        print(f"Database Error: {e}")

# --- 🔐 LOGIN PROTECTION ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# --- 🛠️ AI UTILITIES ---

def analyze_plant(image_bytes):
    # 🌍 Local Ugandan Mapping (Case-Insensitive)
    LOCAL_NAMES = {
        "zea mays": "Maize (Mahindi)",
        "arachis hypogaea": "Groundnuts (Ebinyebwa)",
        "phaseolus vulgaris": "Beans (Bijanjalo)",
        "manihot esculenta": "Cassava (Muwogo)",
        "sorghum bicolor": "Sorghum"
    }

    if not PLANT_ID_API_KEY: return "Maize Sample", 95, "HEALTHY"
    
    encoded = base64.b64encode(image_bytes).decode('ascii')
    payload = {
        "images": [encoded],
        "latitude": 0.3476, "longitude": 32.5825,
        "modifiers": ["crops_fast", "disease_all", "crop_health"]
    }
    
    try:
        res = requests.post("https://api.plant.id/v2/identify", 
                             json=payload, 
                             headers={"Api-Key": PLANT_ID_API_KEY}, 
                             timeout=15)
        data = res.json()
        sug = data['suggestions'][0]
        
        # 🧪 Clean Scientific Name
        raw_sci = sug.get('plant_name', '').strip().lower()
        api_common = sug.get('plant_details', {}).get('common_names', [None])[0]
        
        # 🧪 Mapping Logic
        if raw_sci in LOCAL_NAMES:
            crop_name = LOCAL_NAMES[raw_sci]
        elif api_common:
            crop_name = api_common.title()
        else:
            crop_name = sug['plant_name'].title()

        # 🧪 Health Assessment
        health_data = data.get('health_assessment', {})
        is_healthy = health_data.get('is_healthy', True)
        
        status = "HEALTHY"
        if not is_healthy and health_data.get('diseases'):
            status = health_data['diseases'][0]['name'].upper()
        
        return crop_name, round(sug['probability']*100, 1), status
    except:
        return "Unknown Plant", 0, "SCAN ERROR"

def get_llama_advice(crop, status):
    if not OPENROUTER_KEY: return "Apply mulch and check soil moisture."

    # 🧠 SMART BRAIN UPGRADE: Healthy vs Infected
    if status == "HEALTHY":
        prompt_goal = "Give 3 organic tips to KEEP this plant healthy and MAXIMIZE harvest yield."
        focus = "Focus on mulching, manure, and weeding."
    else:
        prompt_goal = f"This plant has {status}. Give 3 emergency organic remedies to CURE it."
        focus = "Focus on natural sprays (Neem/Chili), removing infected parts, and wood ash."

    prompt = (
        f"You are a Senior Ugandan Agricultural Officer. A farmer scanned a {crop}. "
        f"Status: {status}. {prompt_goal} {focus} "
        f"Keep it practical for a Ugandan village, under 70 words, in 3 bullet points."
    )
    
    try:
        res = requests.post("https://openrouter.ai/api/v1/chat/completions", 
            headers={"Authorization": f"Bearer {OPENROUTER_KEY}"},
            json={
                "model": "meta-llama/llama-3.1-8b-instruct:free", 
                "messages": [{"role": "user", "content": prompt}]
            })
        return res.json()['choices'][0]['message']['content']
    except:
        return "Apply wood ash and consult your sub-county extension officer."

# --- 🚀 ROUTES ---

@app.route('/')
@login_required
def index():
    return render_template('index.html', t={'title': 'Agri-Guard Intelligence'})

@app.route('/predict', methods=['POST'])
@login_required
def predict():
    file = request.files.get('file')
    if not file: return redirect(url_for('index'))
    
    img_bytes = file.read()
    encoded_img = base64.b64encode(img_bytes).decode('utf-8')
    user_image = f"data:image/jpeg;base64,{encoded_img}"
    
    crop, conf, status = analyze_plant(img_bytes)
    advice = get_llama_advice(crop, status)
    
    # DB Log for presentation
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute("INSERT INTO scans (user, crop, status, time) VALUES (?, ?, ?, ?)", 
                     (session['username'], crop, status, datetime.now().strftime("%Y-%m-%d %H:%M")))
        conn.commit()
        conn.close()
    except:
        pass

    return render_template('index.html', 
                           user_image=user_image,
                           prediction=f"{crop} ({conf}%)", 
                           advice=f"CONDITION: {status}", 
                           prescription=advice,
                           t={'title': 'Agri-Guard Intelligence'})

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = request.form.get('username')
        pw = request.form.get('password')
        conn = sqlite3.connect(DB_PATH)
        row = conn.execute("SELECT password FROM users WHERE username = ?", (user,)).fetchone()
        conn.close()
        if row and check_password_hash(row[0], pw):
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
        flash("Success! Please Login.", "success")
    except:
        flash("Username taken.", "error")
    return redirect(url_for('login'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    with app.app_context():
        init_db()
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
