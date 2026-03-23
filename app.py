import os
import sqlite3
import requests
from flask import Flask, render_template, request, session, redirect, url_for, jsonify
from datetime import datetime, timedelta
from functools import wraps

app = Flask(__name__)

# --- 🔐 CONFIG ---
app.secret_key = 'agri_guard_alpha_2026_st_lawrence'
app.permanent_session_lifetime = timedelta(minutes=60)

# Paths
DB_PATH = '/tmp/agriguard.db'
os.makedirs(os.path.join(os.getcwd(), 'static', 'uploads'), exist_ok=True)

# Master Credentials
ADMIN_USER = "admin"
ADMIN_PASS = "StLawrence2026"

# --- 🔑 API KEYS (From Render Env) ---
HF_TOKEN = os.getenv("HUGGINGFACE_API_KEY")
OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY")

# Model IDs
# PlantVillage-optimized model for 38 classes of crop diseases
HF_MODEL_ID = "linkanjarad/mobilenet_v2_1.0_224-plant-disease-identification"
OR_MODEL_ID = "meta-llama/llama-3.1-8b-instruct:free"

# --- 🧪 AI CORE FUNCTIONS ---

def detect_disease(image_bytes):
    """Sends image to Hugging Face Inference API."""
    api_url = f"https://api-inference.huggingface.co/models/{HF_MODEL_ID}"
    headers = {"Authorization": f"Bearer {HF_TOKEN}"}
    response = requests.post(api_url, headers=headers, data=image_bytes)
    return response.json()

def get_treatment_advice(disease_name):
    """Sends detected disease to OpenRouter for South Sudan-specific advice."""
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENROUTER_KEY}",
        "HTTP-Referer": "https://agri-guard.onrender.com",
        "Content-Type": "application/json"
    }
    prompt = (f"The crop has {disease_name}. Provide 3 organic treatment steps "
              "suitable for a farmer in South Sudan (e.g., using Neem, wood ash, or crop rotation).")
    
    payload = {
        "model": OR_MODEL_ID,
        "messages": [{"role": "user", "content": prompt}]
    }
    response = requests.post(url, headers=headers, json=payload)
    return response.json()['choices'][0]['message']['content']

# --- 🛠️ HELPERS ---

def get_ui_context(lang='en'):
    translations = {
        'en': {'title': 'Agri-Guard Intelligence'},
        'sw': {'title': 'Agri-Guard Swahili'},
        'lg': {'title': 'Agri-Guard Luganda'}
    }
    return {
        't': translations.get(lang, translations['en']),
        'current_lang': lang,
        'weather': {'city': 'Kampala', 'temp': '28', 'desc': 'Cloudy'},
        'theme_color': '#28a745'
    }

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute('''CREATE TABLE IF NOT EXISTS scans 
                    (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                     filename TEXT, result TEXT, prescription TEXT, timestamp TEXT)''')
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
    lang = request.args.get('lang', 'en')
    context = get_ui_context(lang)
    try:
        conn = sqlite3.connect(DB_PATH)
        history = conn.execute("SELECT result, timestamp FROM scans ORDER BY id DESC LIMIT 5").fetchall()
        conn.close()
    except: history = []
    return render_template('index.html', history=history, **context)

@app.route('/predict', methods=['POST'])
@login_required
def predict():
    lang = request.form.get('lang', 'en')
    context = get_ui_context(lang)
    file = request.files.get('file')
    
    if not file: return redirect(url_for('index'))

    image_bytes = file.read()
    
    try:
        # Step 1: Detect Disease (Hugging Face)
        hf_results = detect_disease(image_bytes)
        
        # Handle API loading/warmup
        if isinstance(hf_results, dict) and 'estimated_time' in hf_results:
             return render_template('index.html', prediction="AI WARMING UP", 
                                   advice="The Neural Engine is starting. Please try again in 20 seconds.", 
                                   **context)

        top_result = hf_results[0]
        disease_raw = top_result['label'].replace("___", " ").replace("_", " ")
        confidence = round(top_result['score'] * 100, 1)

        # Step 2: Get Treatment (OpenRouter)
        treatment = get_treatment_advice(disease_raw)

        # Log to DB
        conn = sqlite3.connect(DB_PATH)
        conn.execute("INSERT INTO scans (result, prescription, timestamp) VALUES (?, ?, ?)",
                     (disease_raw, treatment, datetime.now().strftime("%Y-%m-%d %H:%M")))
        conn.commit()
        history = conn.execute("SELECT result, timestamp FROM scans ORDER BY id DESC LIMIT 5").fetchall()
        conn.close()

        return render_template('index.html', 
                               prediction=f"{disease_raw} ({confidence}%)", 
                               advice="Biometric Analysis Successful",
                               prescription=treatment,
                               history=history,
                               **context)

    except Exception as e:
        return render_template('index.html', prediction="SYSTEM ERROR", 
                               advice=f"Check API Keys in Render: {str(e)}", **context)

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
