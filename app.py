import os
import io
import base64
import sqlite3
import random
from flask import Flask, render_template, request, session, redirect, url_for, jsonify, flash
from datetime import datetime, timedelta
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)

# --- 🔐 SECURITY & CONFIG ---
# Using the secret key and session lifetime established in your project
app.secret_key = os.environ.get('SECRET_KEY', 'AgriGuard_SLU_2026_Alpha')
app.permanent_session_lifetime = timedelta(minutes=60)

# Paths (Using /tmp/ for Render compatibility as per your IT professional requirements)
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

# --- 📋 FULL KNOWLEDGE BASE (20+ RANDOM SCENARIOS) ---
KNOWLEDGE_BASE = {
    "HEALTHY": [
        {"status": "VIBRANT (98%)", "advice": "Optimal chlorophyll density detected. Photosynthetic rate is peaked.", "prescription": "Maintain current irrigation; no intervention needed."},
        {"status": "STABLE (92%)", "advice": "Consistent leaf turgor pressure. No cellular stress identified.", "prescription": "Standard monitoring. Consider organic mulch for moisture retention."},
        {"status": "ROBUST (95%)", "advice": "Strong stem vascularity and healthy stomata patterns.", "prescription": "Continue existing nutrient cycle. System check: Clear."},
        {"status": "CLEAN (90%)", "advice": "Zero fungal spores or pest signatures found in neural scan.", "prescription": "Apply preventive organic neem wash every 14 days."},
        {"status": "FLOURISHING (97%)", "advice": "Biometric signature shows high metabolic efficiency.", "prescription": "Ensure consistent sunlight exposure. No treatment required."},
        {"status": "HYDRATED (93%)", "advice": "Excellent water-to-tissue ratio. Leaf surface is pristine.", "prescription": "Monitor soil pH levels weekly to maintain this state."},
        {"status": "DORMANT (88%)", "advice": "Plant is healthy but in a low-growth phase.", "prescription": "Reduce nitrogen fertilizer; focus on root-health minerals."},
        {"status": "PRISTINE (99%)", "advice": "Perfect biological symmetry detected by Agri-Guard AI.", "prescription": "Archive this scan as a 'Gold Standard' reference."},
        {"status": "RELIANT (91%)", "advice": "Natural defenses are active and healthy.", "prescription": "Introduce beneficial insects (Ladybugs) for natural protection."},
        {"status": "EFFICIENT (94%)", "advice": "Nutrient absorption levels are in the top 5th percentile.", "prescription": "Continue current localized watering techniques."}
    ],
    "INFECTED": [
        {"status": "FUNGAL BLIGHT (87%)", "advice": "Necrotic lesions detected. Patterns suggest early fungal spread.", "prescription": "Apply copper-based fungicide and remove heavily damaged leaves."},
        {"status": "BACTERIAL WILT (82%)", "advice": "Vascular compromise detected. Signature matches bacterial infection.", "prescription": "Isolate the area. Avoid overhead watering to stop splash-dispersal."},
        {"status": "ARMYWORM ATTACK (89%)", "advice": "Irregular margins match Fall Armyworm feeding patterns.", "prescription": "Apply Bacillus thuringiensis (Bt) or biopesticides immediately."},
        {"status": "POWDERY MILDEW (78%)", "advice": "White mycelium patches detected on the leaf surface.", "prescription": "Spray a mixture of baking soda, liquid soap, and water."},
        {"status": "RUST DISEASE (75%)", "advice": "Orange/Brown pustules found. Spore dispersal is active.", "prescription": "Dust with sulfur powder and improve air circulation."},
        {"status": "APHID INFESTATION (84%)", "advice": "Cluster signatures on leaf undersides suggest sap-sucking pests.", "prescription": "Use high-pressure water spray followed by insecticidal soap."},
        {"status": "MOSAIC VIRUS (71%)", "advice": "Mottled yellow/green patterns suggest viral compromise.", "prescription": "Remove and burn infected plants. Disinfect all farming tools."},
        {"status": "NUTRIENT DEFICIENCY (68%)", "advice": "Interveinal chlorosis suggests a severe lack of Magnesium.", "prescription": "Apply Epsom salts (Magnesium Sulfate) to the soil base."},
        {"status": "LEAF SPOT (80%)", "advice": "Circular brown spots with yellow halos detected.", "prescription": "Increase plant spacing and apply a broad-spectrum fungicide."},
        {"status": "SOOTY MOLD (74%)", "advice": "Black sticky film indicates secondary infection from pests.", "prescription": "Treat for Whiteflies/Aphids first, then wipe leaves with damp cloth."}
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
    weather_data = {'city': 'Kampala', 'temp': '28', 'desc': 'Partly Cloudy'}
    t_content = {'title': 'Agri-Guard Intelligence'}
    return render_template('index.html', current_lang=lang, weather=weather_data, t=t_content)

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
    
    # 🎲 RANDOM LOGIC ENGINE
    # We select category, then a random outcome with all 3 required fields
    category = "INFECTED" if random.random() > 0.4 else "HEALTHY"
    result = random.choice(KNOWLEDGE_BASE[category])
    
    # Image processing for display
    img_bytes = file.read()
    encoded_img = base64.b64encode(img_bytes).decode('utf-8')
    user_image = f"data:image/jpeg;base64,{encoded_img}"

    return render_template('index.html', 
                           prediction=result['status'], 
                           advice=result['advice'], 
                           prescription=result['prescription'],
                           user_image=user_image,
                           current_lang=request.form.get('lang', 'en'),
                           weather={'city': 'Kampala', 'temp': '28', 'desc': 'Partly Cloudy'},
                           t={'title': 'Agri-Guard Intelligence'})

@app.route('/analytics_data')
@login_required
def analytics_data():
    # Feeds the Chart.js doughnut chart with randomized values for a dynamic demo
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
    # Configured for Render deployment
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
