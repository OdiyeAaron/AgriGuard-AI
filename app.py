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
app.secret_key = 'agri_guard_st_lawrence_2026'
app.permanent_session_lifetime = timedelta(minutes=60)

# Ensure paths use the correct folder structure
UPLOAD_FOLDER = os.path.join('static', 'uploads')
DATASET_FOLDER = 'dataset'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

ADMIN_USER = "admin"
ADMIN_PASS = "StLawrence2026"

WEATHER_API_KEY = "488852ae787287c13660dcb6ed547f6e"
CITY = "Kampala"

# Create necessary directories
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

def save_for_training(filepath, label):
    label_dir = os.path.join(DATASET_FOLDER, label.lower().replace(" ", "_"))
    os.makedirs(label_dir, exist_ok=True)
    shutil.copy(filepath, os.path.join(label_dir, os.path.basename(filepath)))

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

# --- 🧠 FEATURE EXTRACTION ---
def extract_features(filepath):
    img = cv2.imread(filepath)
    if img is None:
        return None

    img = cv2.resize(img, (300, 300))
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    total = 300 * 300

    # Color ranges
    green = cv2.inRange(hsv, (35, 40, 40), (85, 255, 255))
    green_score = cv2.countNonZero(green) / total * 100

    brown = cv2.inRange(hsv, (10, 40, 40), (30, 255, 255))
    brown_score = cv2.countNonZero(brown) / total * 100

    # Mold: Balanced brightness trigger
    mold = cv2.inRange(hsv, (0, 0, 0), (180, 255, 40))
    mold_score = cv2.countNonZero(mold) / total * 100

    edges = cv2.Canny(gray, 100, 200)
    edge_score = cv2.countNonZero(edges) / total * 100

    texture = np.std(gray)

    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    objects = len(contours)

    return [green_score, brown_score, mold_score, edge_score, texture, objects]

# --- 🚀 ROUTES ---

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        u = request.form['username'].lower().strip()
        p = request.form['password'].strip()
        if u == ADMIN_USER and p == ADMIN_PASS:
            session['logged_in'] = True
            return redirect(url_for('index'))
        
        conn = sqlite3.connect('agriguard.db')
        user = conn.execute("SELECT * FROM users WHERE username=? AND password=?", (u, p)).fetchone()
        conn.close()
        if user:
            session['logged_in'] = True
            return redirect(url_for('index'))
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('login'))

@app.route('/')
def home():
    return redirect(url_for('index'))

@app.route('/index')
@login_required
def index():
    conn = sqlite3.connect('agriguard.db')
    history = conn.execute("SELECT result, timestamp FROM scans ORDER BY id DESC LIMIT 5").fetchall()
    conn.close()
    return render_template('index.html', history=history, t=TRANSLATIONS['en'], current_lang='en', weather=get_weather())

@app.route('/predict', methods=['POST'])
@login_required
def predict():
    try:
        if 'file' not in request.files:
            return "No file part"
        
        file = request.files['file']
        if file.filename == '':
            return "No selected file"

        if file and allowed_file(file.filename):
            filename = file.filename
            save_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(save_path)

            f = extract_features(save_path)
            if f is None:
                return "Processing Error"

            green, brown, mold, edges, texture, objects = f
            severity, cause, solution, color = "Low", "Unknown", "No action needed", "#28a745"

            # --- AI LOGIC ENGINE ---
            # 1. Reject Synthetic (Shirt Filter)
            if objects < 5 or texture < 15:
                result, msg, color = "INVALID OBJECT", "Synthetic material detected", "#666"
                cause, solution = "Non-organic surface", "Please scan real crop material"

            # 2. Leaf Detection
            elif green > 15:
                if mold > 15:
                    result, msg, color = "DISEASE DETECTED", "Fungal infection", "#dc3545"
                    severity, solution = "Severe", "Apply fungicide"
                elif edges > 20:
                    result, msg, color = "DISEASE DETECTED", "Pest attack", "#ffc107"
                    severity, solution = "Moderate", "Use organic pesticide"
                else:
                    result, msg = "HEALTHY CROP", "Leaf is healthy"

            # 3. Seed Detection
            elif brown > 8 or edges > 2:
                if mold > 11: # High sensitivity for seed rot
                    result, msg, color = "INFECTED SEEDS", "Contamination detected", "#c82333"
                    severity, solution = "Severe", "Discard or treat with Mancozeb"
                else:
                    result, msg, color = "VIABLE SEEDS", "Seeds are healthy", "#8b4513"
                    solution = "Store in dry, cool conditions"
            
            else:
                result, msg, color = "INVALID OBJECT", "Unknown object", "#666"

            # Save to Database
            save_for_training(save_path, result)
            conn = sqlite3.connect('agriguard.db')
            now = datetime.now().strftime("%Y-%m-%d %H:%M")
            conn.execute("INSERT INTO scans (filename, result, advice, timestamp) VALUES (?, ?, ?, ?)",
                         (filename, result, msg, now))
            conn.commit()
            history = conn.execute("SELECT result, timestamp FROM scans ORDER BY id DESC LIMIT 5").fetchall()
            conn.close()

            # Format image path for HTML
            image_url = url_for('static', filename='uploads/' + filename)

            return render_template('index.html',
                                   prediction=result,
                                   advice=msg,
                                   cause=cause,
                                   prescription=solution,
                                   severity=severity,
                                   theme_color=color,
                                   image_path=image_url,
                                   history=history,
                                   t=TRANSLATIONS['en'],
                                   current_lang='en',
                                   weather=get_weather())
        else:
            return "Invalid file format. Please upload JPG or PNG."

    except Exception as e:
        return f"Server Error: {str(e)}"

@app.route('/analytics_data')
@login_required
def analytics_data():
    conn = sqlite3.connect('agriguard.db')
    rows = conn.execute("SELECT result, COUNT(*) FROM scans GROUP BY result").fetchall()
    conn.close()
    return jsonify({'labels': [r[0] for r in rows], 'values': [r[1] for r in rows]})

if __name__ == '__main__':
    # host 0.0.0.0 allows access from your phone on the same WiFi
    app.run(debug=True, host='0.0.0.0', port=5000)