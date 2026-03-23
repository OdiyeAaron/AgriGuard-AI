from flask import Flask, render_template, request, jsonify, session, redirect, url_for
import os
import cv2
import numpy as np
import sqlite3
import requests
import shutil
from datetime import datetime, timedelta
from functools import wraps

app = Flask(__name__)

# --- 🔐 SECURITY & CONFIG ---
# This key secures your sessions at St. Lawrence University
app.secret_key = 'agri_guard_st_lawrence_2026_alpha_aaron'
app.permanent_session_lifetime = timedelta(minutes=60)

UPLOAD_FOLDER = os.path.join('static', 'uploads')
DATASET_FOLDER = 'dataset'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Master Admin Credentials
ADMIN_USER = "admin"
ADMIN_PASS = "StLawrence2026"

# Weather Integration for Kampala
WEATHER_API_KEY = "488852ae787287c13660dcb6ed547f6e"
CITY = "Kampala"

# Initialize Directories
for folder in [UPLOAD_FOLDER, DATASET_FOLDER]:
    os.makedirs(folder, exist_ok=True)

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

# --- 🌍 TRANSLATIONS ---
TRANSLATIONS = {
    'en': {
        'title': 'Agri-Guard AI',
        'tap_to_scan': 'Tap to Scan Leaf or Seed',
        'history': 'Recent Activity Log',
        'footer': 'Powered by Flask & AI',
        'healthy': 'HEALTHY CROP',
        'disease': 'DISEASE DETECTED',
        'seeds': 'VIABLE SEEDS',
        'infected': 'INFECTED SEEDS',
        'invalid': 'INVALID OBJECT',
        'treatment_label': 'Recommended Action:',
        'severity_label': 'Severity Level:',
        'low': 'Low',
        'medium': 'Moderate',
        'high': 'Severe',
        'no_treatment': 'No treatment required.',
        'rust_treatment': 'Apply Copper fungicide or Neem Oil.',
        'seed_treatment': 'Treat seeds with Mancozeb or discard.'
    }
}

# --- 📊 DATABASE ---
def init_db():
    conn = sqlite3.connect('agriguard.db')
    cursor = conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS scans (id INTEGER PRIMARY KEY AUTOINCREMENT, filename TEXT, result TEXT, advice TEXT, timestamp TEXT)')
    cursor.execute('CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE, password TEXT)')
    conn.commit()
    conn.close()

init_db()

def get_weather():
    try:
        url = f"http://api.openweathermap.org/data/2.5/weather?q={CITY}&appid={WEATHER_API_KEY}&units=metric"
        response = requests.get(url, timeout=3)
        data = response.json()
        if response.status_code == 200:
            return {
                "temp": round(data['main']['temp']),
                "desc": data['weather'][0]['description'].capitalize(),
                "city": CITY
            }
    except:
        pass
    return {"temp": "--", "desc": "Offline", "city": CITY}

# --- 🧠 FEATURE EXTRACTION (OpenCV) ---
def extract_features(filepath):
    img = cv2.imread(filepath)
    if img is None: return None
    img = cv2.resize(img, (300, 300))
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    total = 300 * 300

    # AI Detection Metrics
    green = cv2.countNonZero(cv2.inRange(hsv, (35, 40, 40), (85, 255, 255))) / total * 100
    brown = cv2.countNonZero(cv2.inRange(hsv, (10, 40, 40), (30, 255, 255))) / total * 100
    mold = cv2.countNonZero(cv2.inRange(hsv, (0, 0, 0), (180, 255, 40))) / total * 100
    edges = cv2.countNonZero(cv2.Canny(gray, 100, 200)) / total * 100
    texture = np.std(gray)
    contours, _ = cv2.findContours(cv2.Canny(gray, 100, 200), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    return [green, brown, mold, edges, texture, len(contours)]

# --- 🚀 ROUTES ---

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        u = request.form['username'].lower().strip()
        p = request.form['password'].strip()
        
        # Admin Logic
        if u == ADMIN_USER and p == ADMIN_PASS:
            session['logged_in'] = True
            session['username'] = ADMIN_USER
            return redirect(url_for('index'))
        
        # Farmer Logic
        conn = sqlite3.connect('agriguard.db')
        user = conn.execute("SELECT * FROM users WHERE username=? AND password=?", (u, p)).fetchone()
        conn.close()
        if user:
            session['logged_in'] = True
            session['username'] = u
            return redirect(url_for('index'))
        
        return render_template('login.html', error="Invalid username or password")
    return render_template('login.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        u = request.form['username'].lower().strip()
        p = request.form['password'].strip()
        try:
            conn = sqlite3.connect('agriguard.db')
            conn.execute("INSERT INTO users (username, password) VALUES (?, ?)", (u, p))
            conn.commit()
            conn.close()
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            return render_template('signup.html', error="Username already exists!")
    return render_template('signup.html')

@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        u = request.form['username'].lower().strip()
        p = request.form['new_password'].strip()
        conn = sqlite3.connect('agriguard.db')
        user = conn.execute("SELECT * FROM users WHERE username=?", (u,)).fetchone()
        if user:
            conn.execute("UPDATE users SET password=? WHERE username=?", (p, u))
            conn.commit()
            conn.close()
            return render_template('forgot_password.html', message="Password updated successfully!")
        conn.close()
        return render_template('forgot_password.html', error="User not found.")
    return render_template('forgot_password.html')

@app.route('/admin-console')
@login_required
def admin_console():
    if session.get('username') != ADMIN_USER:
        return "Access Denied", 403
    conn = sqlite3.connect('agriguard.db')
    users = conn.execute("SELECT id, username FROM users").fetchall()
    scans = conn.execute("SELECT timestamp, result, advice FROM scans ORDER BY id DESC").fetchall()
    conn.close()
    return render_template('admin.html', users=users, scans=scans)

@app.route('/')
@app.route('/index')
@login_required
def index():
    conn = sqlite3.connect('agriguard.db')
    history = conn.execute("SELECT result, timestamp FROM scans ORDER BY id DESC LIMIT 5").fetchall()
    conn.close()
    return render_template('index.html', history=history, t=TRANSLATIONS['en'], weather=get_weather())

@app.route('/predict', methods=['POST'])
@login_required
def predict():
    file = request.files.get('file')
    if not file or not allowed_file(file.filename):
        return "Invalid File", 400

    filename = datetime.now().strftime("%Y%m%d_%H%M%S_") + file.filename
    save_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(save_path)

    f = extract_features(save_path)
    if not f: return "Processing Error", 500

    green, brown, mold, edges, texture, objects = f
    severity, cause, solution, color = "Low", "Natural", "No action needed", "#28a745"

    # AI Decision Tree
    if objects < 5 or texture < 15:
        result, msg, color = "INVALID OBJECT", "Synthetic material detected", "#666"
    elif green > 15:
        if mold > 15:
            result, msg, color, severity, solution = "DISEASE DETECTED", "Fungal infection", "#dc3545", "Severe", "Apply fungicide"
        elif edges > 20:
            result, msg, color, severity, solution = "DISEASE DETECTED", "Pest attack", "#ffc107", "Moderate", "Use organic pesticide"
        else:
            result, msg = "HEALTHY CROP", "Leaf is healthy"
    elif brown > 8:
        if mold > 11:
            result, msg, color, severity, solution = "INFECTED SEEDS", "Contamination detected", "#c82333", "Severe", "Discard or treat"
        else:
            result, msg, color, solution = "VIABLE SEEDS", "Seeds are healthy", "#8b4513", "Store in dry conditions"
    else:
        result, msg, color = "INVALID OBJECT", "Unknown object", "#666"

    # Save Diagnostic to DB
    conn = sqlite3.connect('agriguard.db')
    conn.execute("INSERT INTO scans (filename, result, advice, timestamp) VALUES (?, ?, ?, ?)",
                 (filename, result, msg, datetime.now().strftime("%Y-%m-%d %H:%M")))
    conn.commit()
    history = conn.execute("SELECT result, timestamp FROM scans ORDER BY id DESC LIMIT 5").fetchall()
    conn.close()

    return render_template('index.html', prediction=result, advice=msg, cause=cause, prescription=solution, 
                           severity=severity, theme_color=color, image_path=url_for('static', filename='uploads/'+filename),
                           history=history, t=TRANSLATIONS['en'], weather=get_weather())

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
