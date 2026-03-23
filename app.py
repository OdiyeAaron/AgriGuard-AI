import os
import cv2
import numpy as np
import sqlite3
import requests
import joblib
import google.generativeai as genai
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from datetime import datetime, timedelta
from functools import wraps

app = Flask(__name__)

# --- 🔐 SECURITY & CONFIG ---
app.secret_key = 'agri_guard_st_lawrence_2026_alpha_aaron'
app.permanent_session_lifetime = timedelta(minutes=60)

UPLOAD_FOLDER = os.path.join('static', 'uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Master Admin Credentials
ADMIN_USER = "admin"
ADMIN_PASS = "StLawrence2026"

# Weather Integration (OpenWeatherMap)
WEATHER_API_KEY = "488852ae787287c13660dcb6ed547f6e"
CITY = "Kampala"

# --- 🤖 AI CONFIGURATION ---
GEMINI_KEY = os.getenv("GEMINI_API_KEY", "YOUR_FALLBACK_KEY_HERE")
genai.configure(api_key=GEMINI_KEY)
gemini_model = genai.GenerativeModel('gemini-1.5-flash')

# --- 🧠 MODEL LOADING (WITH 500-ERROR PROTECTION) ---
class FallbackModel:
    def predict(self, features): return [2] # Default to "Invalid" if real model is missing

try:
    model_brain = joblib.load('models/leaf_model.pkl')
    print("✅ XGBoost Brain Loaded Successfully")
except Exception as e:
    print(f"⚠️ CRITICAL: leaf_model.pkl not found. Using Fallback Mode. Error: {e}")
    model_brain = FallbackModel()

# Initialize Directories
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# --- 🛡️ UTILITIES ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# --- 📊 DATABASE & AUTO-REPAIR ---
def init_db():
    conn = sqlite3.connect('agriguard.db')
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS scans 
                      (id INTEGER PRIMARY KEY AUTOINCREMENT, filename TEXT, result TEXT, 
                       advice TEXT, prescription TEXT, timestamp TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS users 
                      (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE, password TEXT)''')
    
    # 🔥 REPAIR LOGIC: This fixes the 500 error by adding the missing column automatically
    try:
        cursor.execute("SELECT prescription FROM scans LIMIT 1")
    except sqlite3.OperationalError:
        print("🛠️ Repairing Database: Adding 'prescription' column...")
        cursor.execute("ALTER TABLE scans ADD COLUMN prescription TEXT")
        conn.commit()
            
    conn.commit()
    conn.close()

init_db()

def get_weather():
    try:
        url = f"http://api.openweathermap.org/data/2.5/weather?q={CITY}&appid={WEATHER_API_KEY}&units=metric"
        response = requests.get(url, timeout=3)
        data = response.json()
        if response.status_code == 200:
            return {"temp": round(data['main']['temp']), "desc": data['weather'][0]['description'].capitalize(), "city": CITY}
    except: pass
    return {"temp": "--", "desc": "Offline", "city": CITY}

# --- 🧠 10-FEATURE EXTRACTION ---
def extract_10_features(filepath):
    img = cv2.imread(filepath)
    if img is None: return None
    img = cv2.resize(img, (300, 300))
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    total = 300 * 300

    green = cv2.countNonZero(cv2.inRange(hsv, (35, 40, 40), (85, 255, 255))) / total * 100
    brown = cv2.countNonZero(cv2.inRange(hsv, (10, 40, 40), (30, 255, 255))) / total * 100
    mold = cv2.countNonZero(cv2.inRange(hsv, (0, 0, 0), (180, 255, 40))) / total * 100
    edges = cv2.countNonZero(cv2.Canny(gray, 100, 200)) / total * 100
    texture = np.std(gray)
    contours, _ = cv2.findContours(cv2.Canny(gray, 100, 200), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    objects = len(contours)

    red = cv2.countNonZero(cv2.inRange(hsv, (0, 50, 50), (10, 255, 255))) / total * 100
    yellow = cv2.countNonZero(cv2.inRange(hsv, (20, 100, 100), (30, 255, 255))) / total * 100
    flipped = cv2.flip(gray, 1)
    symmetry = 100 - (np.sum(cv2.absdiff(gray, flipped)) / (total * 255) * 100)
    contrast = float(gray.max() - gray.min())

    return [green, brown, mold, edges, texture, objects, red, yellow, symmetry, contrast]

# --- 💬 GEMINI AGRO-ADVICE ---
def get_gemini_prescription(status, details):
    prompt = f"Role: Professional AI Agronomist. Status: {status}. Observation: {details}. Provide 3 bullet points for maintenance or treatment. Max 80 words."
    try:
        response = gemini_model.generate_content(prompt)
        return response.text
    except Exception as e:
        print(f"Gemini Error: {e}")
        return "⚠️ Keep in cool, dry conditions and consult a local agricultural officer."

# --- 🚀 ROUTES ---

@app.route('/')
@login_required
def index():
    conn = sqlite3.connect('agriguard.db')
    history = conn.execute("SELECT result, timestamp FROM scans ORDER BY id DESC LIMIT 5").fetchall()
    conn.close()
    return render_template('index.html', history=history, weather=get_weather())

@app.route('/predict', methods=['POST'])
@login_required
def predict():
    file = request.files.get('file')
    if not file or not allowed_file(file.filename): return redirect(url_for('index'))

    filename = datetime.now().strftime("%Y%m%d_%H%M%S_") + file.filename
    save_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(save_path)

    features = extract_10_features(save_path)
    if not features: return "Processing Error", 500

    # 1. Prediction
    pred_idx = model_brain.predict([features])[0]
    mapping = {
        0: ("DISEASE DETECTED", "Biological fungal/pest stress", "#dc3545"),
        1: ("HEALTHY LEAF", "High chlorophyll & symmetry", "#28a745"),
        2: ("INVALID OBJECT", "Non-agricultural material", "#666"),
        3: ("HEALTHY SEEDS", "Viable grain structure", "#10b981")
    }
    res_title, res_desc, res_color = mapping.get(pred_idx, ("UNKNOWN", "Scan again", "#666"))

    # 2. Advice & Database Save
    prescription = get_gemini_prescription(res_title, res_desc)
    conn = sqlite3.connect('agriguard.db')
    conn.execute("INSERT INTO scans (filename, result, advice, prescription, timestamp) VALUES (?, ?, ?, ?, ?)",
                 (filename, res_title, res_desc, prescription, datetime.now().strftime("%Y-%m-%d %H:%M")))
    conn.commit()
    history = conn.execute("SELECT result, timestamp FROM scans ORDER BY id DESC LIMIT 5").fetchall()
    conn.close()

    return render_template('index.html', prediction=res_title, advice=res_desc, 
                           prescription=prescription, theme_color=res_color, 
                           image_path=url_for('static', filename='uploads/'+filename),
                           history=history, weather=get_weather())

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        u, p = request.form['username'].lower().strip(), request.form['password'].strip()
        if u == ADMIN_USER and p == ADMIN_PASS:
            session.update({'logged_in': True, 'username': ADMIN_USER})
            return redirect(url_for('index'))
        conn = sqlite3.connect('agriguard.db')
        user = conn.execute("SELECT * FROM users WHERE username=? AND password=?", (u, p)).fetchone()
        conn.close()
        if user:
            session.update({'logged_in': True, 'username': u})
            return redirect(url_for('index'))
        return render_template('login.html', error="Invalid Credentials")
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
