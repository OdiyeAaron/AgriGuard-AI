import os
import io
import json
import base64
import requests
import sqlite3
from flask import Flask, render_template, request, session, redirect, url_for, jsonify
from datetime import datetime, timedelta
from functools import wraps
from PIL import Image

app = Flask(__name__)
app.secret_key = 'agriguard_st_lawrence_2026'
app.permanent_session_lifetime = timedelta(minutes=60)

# Paths
DB_PATH = '/tmp/agriguard.db'
os.makedirs(os.path.join(os.getcwd(), 'static', 'uploads'), exist_ok=True)

# Master Credentials
ADMIN_USER = "admin"
ADMIN_PASS = "StLawrence2026"

# --- 🔑 API CONFIG ---
# Make sure these are set in your Render Environment Variables
PLANT_ID_API_KEY = os.getenv("PLANT_ID_API_KEY")
OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY")

def analyze_with_plant_id(image_bytes):
    """Expert AI Engine for Maize, Beans, Rice, Sorghum, Groundnuts, and Coffee."""
    if not PLANT_ID_API_KEY:
        return "API Key Missing", 0
    
    encoded_image = base64.b64encode(image_bytes).decode('ascii')
    url = "https://api.plant.id/v2/identify"
    
    payload = {
        "images": [encoded_image],
        "modifiers": ["crops_fast", "disease_all"],
        "plant_details": ["common_names"]
    }
    headers = {"Content-Type": "application/json", "Api-Key": PLANT_ID_API_KEY}

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=20)
        data = response.json()
        
        # Get the best agricultural match
        suggestion = data['suggestions'][0]
        plant_name = suggestion['plant_name']
        probability = round(suggestion['probability'] * 100, 1)
        
        # Check Health Status
        health = data.get('health_assessment', {})
        is_healthy = health.get('is_healthy', True)
        status = "HEALTHY" if is_healthy else "DISEASE DETECTED"
        
        return f"{plant_name} ({status})", probability
    except Exception as e:
        print(f"Plant.id Error: {e}")
        return "Analysis Error", 0

def get_treatment_advice(analysis_result):
    """Localized advice from OpenRouter."""
    if not OPENROUTER_KEY:
        return "Apply wood ash and ensure proper drainage."
        
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {"Authorization": f"Bearer {OPENROUTER_KEY}", "Content-Type": "application/json"}
    
    prompt = (f"The AI detected: '{analysis_result}'. Provide 3 clear, organic treatment steps "
              "for a farmer in South Sudan using local materials like neem oil or wood ash.")
    
    try:
        res = requests.post(url, headers=headers, json={
            "model": "meta-llama/llama-3.1-8b-instruct:free",
            "messages": [{"role": "user", "content": prompt}]
        }, timeout=15)
        return res.json()['choices'][0]['message']['content']
    except:
        return "Ensure crop rotation and apply organic compost to strengthen the plant."

# --- 🛠️ HELPERS & AUTH ---

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

# --- 🚀 ROUTES ---

@app.route('/')
@login_required
def index():
    context = {
        't': {'title': 'Agri-Guard Pro'},
        'weather': {'city': 'Kampala', 'temp': '28', 'desc': 'Sunny'}
    }
    return render_template('index.html', **context)

@app.route('/predict', methods=['POST'])
@login_required
def predict():
    file = request.files.get('file')
    if not file: return redirect(url_for('index'))

    try:
        image_bytes = file.read()
        
        # 🥇 STEP 1: Expert Identification (Plant.id)
        result_text, confidence = analyze_with_plant_id(image_bytes)
        
        # 🥈 STEP 2: Localized Treatment (OpenRouter)
        treatment = get_treatment_advice(result_text)

        return render_template('index.html', 
                               prediction=f"{result_text} ({confidence}%)", 
                               advice="PLANT.ID BIOMETRIC ENGINE COMPLETE",
                               prescription=treatment,
                               t={'title': 'Agri-Guard Pro'},
                               weather={'city': 'Kampala', 'temp': '28', 'desc': 'Sunny'})

    except Exception as e:
        return render_template('index.html', prediction="ANALYSIS FAILED", 
                               advice="Check your API connection.", prescription=str(e),
                               t={'title': 'Agri-Guard Pro'}, weather={'city': 'Kampala', 'temp': '28', 'desc': 'Sunny'})

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
