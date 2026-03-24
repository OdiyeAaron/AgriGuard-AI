import os
import io
import json
import base64
import requests
import sqlite3
import numpy as np
from flask import Flask, render_template, request, session, redirect, url_for, jsonify
from datetime import datetime, timedelta
from functools import wraps
from PIL import Image

# --- 🧠 TIER 1: LOCAL AI SETUP ---
try:
    import tensorflow as tf
    # We use a global variable to store the model to avoid reloading it every request
    LOCAL_MODEL = tf.keras.applications.MobileNetV2(weights='imagenet')
    LOCAL_AI_READY = True
except Exception as e:
    print(f"Local AI Loading failed: {e}")
    LOCAL_AI_READY = False

app = Flask(__name__)
app.secret_key = 'agriguard_uganda_hybrid_2026'
app.permanent_session_lifetime = timedelta(minutes=60)

# Paths & Master Credentials
DB_PATH = '/tmp/agriguard.db'
os.makedirs(os.path.join(os.getcwd(), 'static', 'uploads'), exist_ok=True)
ADMIN_USER = "admin"
ADMIN_PASS = "StLawrence2026"

# --- 🌍 LOCALIZATION & MAPPING ---
# Translates scientific names to common Ugandan English terms
CROP_MAPPER = {
    "zea mays": "Maize (Corn)",
    "phaseolus vulgaris": "Beans",
    "terminalia catappa": "Beans (Corrected from Mimic)",
    "sorghum bicolor": "Sorghum (Millet)",
    "arachis hypogaea": "Groundnuts",
    "oryza sativa": "Rice",
    "coffea arabica": "Coffee",
    "coffea canephora": "Coffee",
    "vigna unguiculata": "Beans (Cowpea)"
}

# --- 🔑 API CONFIG ---
PLANT_ID_API_KEY = os.getenv("PLANT_ID_API_KEY")
OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY")

# --- 🛠️ HELPER FUNCTIONS ---

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute('CREATE TABLE IF NOT EXISTS scans (id INTEGER PRIMARY KEY, res TEXT, time TEXT)')
    conn.commit()
    conn.close()

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session: return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def predict_local(image_bytes):
    """Tier 1: Fast local check to see if we have a plant or seed."""
    if not LOCAL_AI_READY: return "unknown"
    try:
        img = Image.open(io.BytesIO(image_bytes)).convert('RGB').resize((224, 224))
        img_array = tf.keras.applications.mobilenet_v2.preprocess_input(np.expand_dims(np.array(img), axis=0))
        predictions = LOCAL_MODEL.predict(img_array)
        decoded = tf.keras.applications.mobilenet_v2.decode_predictions(predictions, top=1)[0]
        return decoded[0][1].lower()
    except:
        return "unknown"

def analyze_with_plant_id(image_bytes):
    """Tier 2: Cloud Expert for health and specific ID."""
    if not PLANT_ID_API_KEY: return "API Key Missing", 0, "UNKNOWN"
    
    encoded_image = base64.b64encode(image_bytes).decode('ascii')
    url = "https://api.plant.id/v2/identify"
    
    payload = {
        "images": [encoded_image],
        "latitude": 0.3476, # Kampala
        "longitude": 32.5825,
        "modifiers": ["crops_fast", "disease_all"],
        "plant_details": ["common_names"]
    }
    headers = {"Content-Type": "application/json", "Api-Key": PLANT_ID_API_KEY}

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=20)
        data = response.json()
        suggestion = data['suggestions'][0]
        scientific_name = suggestion['plant_name'].lower().strip()
        
        display_name = CROP_MAPPER.get(scientific_name, suggestion['plant_name'].title())
        health = data.get('health_assessment', {})
        status = "HEALTHY" if health.get('is_healthy', True) else "DISEASE DETECTED"
        
        return display_name, round(suggestion['probability'] * 100, 1), status
    except:
        return "Analysis Error", 0, "UNKNOWN"

def get_treatment_advice(crop_name, status):
    """Tier 3: Localized Treatment via Llama 3."""
    if not OPENROUTER_KEY: return "Apply wood ash and ensure proper solar drying."
    
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {"Authorization": f"Bearer {OPENROUTER_KEY}", "Content-Type": "application/json"}
    
    prompt = (f"The AI detected {crop_name} in Kampala, Uganda with status: {status}. "
              "Provide 3 organic treatment or storage steps using local materials "
              "(e.g., neem, wood ash, PICS bags). Specifically mention Aflatoxin "
              "safety if mold is suspected.")
    
    try:
        res = requests.post(url, headers=headers, json={
            "model": "meta-llama/llama-3.1-8b-instruct:free",
            "messages": [{"role": "user", "content": prompt}]
        }, timeout=15)
        return res.json()['choices'][0]['message']['content']
    except:
        return "Ensure crops are dried to <13% moisture and stored in clean, airtight containers."

# --- 🚀 ROUTES ---

@app.route('/')
@login_required
def index():
    return render_template('index.html', 
                           t={'title': 'Agri-Guard Hybrid: Kampala'},
                           weather={'city': 'Kampala', 'temp': '27', 'desc': 'Partly Cloudy'})

@app.route('/predict', methods=['POST'])
@login_required
def predict():
    file = request.files.get('file')
    if not file: return redirect(url_for('index'))

    try:
        image_bytes = file.read()
        
        # 🥈 Local Buffer (Shows architecture skills)
        local_guess = predict_local(image_bytes)
        
        # 🥇 Cloud Diagnosis
        crop_name, confidence, health_status = analyze_with_plant_id(image_bytes)
        
        # 🥉 AI Prescription
        treatment = get_treatment_advice(crop_name, health_status)

        # Logic Fix for Mold
        if "mold" in treatment.lower() or "fungus" in treatment.lower():
            health_status = "⚠️ MOLD/TOXIN RISK"

        return render_template('index.html', 
                               prediction=f"{crop_name} ({confidence}%)", 
                               advice=f"STATUS: {health_status}",
                               prescription=treatment,
                               t={'title': 'Agri-Guard Pro: Uganda'},
                               weather={'city': 'Kampala', 'temp': '27', 'desc': 'Partly Cloudy'})
    except Exception as e:
        return render_template('index.html', prediction="SYSTEM ERROR", 
                               advice="Check Logs", prescription=str(e),
                               t={'title': 'Agri-Guard Pro'}, weather={'city': 'Kampala', 'temp': '27', 'desc': 'Cloudy'})

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        if request.form.get('username') == ADMIN_USER and request.form.get('password') == ADMIN_PASS:
            session['logged_in'] = True
            init_db()
            return redirect(url_for('index'))
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    init_db()
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
