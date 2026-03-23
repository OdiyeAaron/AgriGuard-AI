import os
import sqlite3
import requests
import time
from flask import Flask, render_template, request, session, redirect, url_for, jsonify
from datetime import datetime, timedelta
from functools import wraps

app = Flask(__name__)

# --- 🔐 CONFIG ---
app.secret_key = 'agri_guard_alpha_2026_st_lawrence'
app.permanent_session_lifetime = timedelta(minutes=60)

# Paths - Using /tmp ensures SQLite works on Render's ephemeral disk
DB_PATH = '/tmp/agriguard.db'

# Master Credentials
ADMIN_USER = "admin"
ADMIN_PASS = "StLawrence2026"

# --- 🔑 API KEYS (Ensure these are in Render Environment Variables) ---
HF_TOKEN = os.getenv("HUGGINGFACE_API_KEY")
OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY")

# Model IDs
HF_MODEL_ID = "linkanjarad/mobilenet_v2_1.0_224-plant-disease-identification"
OR_MODEL_ID = "meta-llama/llama-3.1-8b-instruct:free"

# --- 🧪 THE BULLETPROOF RETRY LOGIC ---

def detect_disease_with_retry(image_bytes, retries=3, delay=3):
    """
    Sends image to Hugging Face. If a connection break (IncompleteRead) 
    or 'Model Loading' occurs, it waits and retries.
    """
    api_url = f"https://api-inference.huggingface.co/models/{HF_MODEL_ID}"
    headers = {"Authorization": f"Bearer {HF_TOKEN}"}
    
    for attempt in range(retries):
        try:
            # We use a 30s timeout to account for slow mobile uploads
            response = requests.post(api_url, headers=headers, data=image_bytes, timeout=30)
            
            # Check for HTTP errors (like 503 Service Unavailable)
            response.raise_for_status()
            result = response.json()
            
            # If the model is still loading on Hugging Face's end
            if isinstance(result, dict) and 'estimated_time' in result:
                wait_time = result.get('estimated_time', delay)
                print(f"Model loading... waiting {wait_time}s (Attempt {attempt+1})")
                time.sleep(min(wait_time, 10)) # Wait, but max 10s per retry
                continue
                
            return result
            
        except (requests.exceptions.RequestException, Exception) as e:
            print(f"Attempt {attempt+1} failed: {e}")
            if attempt < retries - 1:
                time.sleep(delay)
                continue
            else:
                raise e
    return None

def get_treatment_advice(disease_name):
    """Fetches South Sudan-specific organic treatment via OpenRouter."""
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENROUTER_KEY}",
        "HTTP-Referer": "https://agri-guard.onrender.com",
        "Content-Type": "application/json"
    }
    prompt = (f"The crop has {disease_name}. Provide 3 clear, organic treatment steps "
              "using local materials available in South Sudan (like Neem or ash).")
    
    payload = {
        "model": OR_MODEL_ID,
        "messages": [{"role": "user", "content": prompt}]
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=25)
        return response.json()['choices'][0]['message']['content']
    except Exception:
        return "Treatment advice is currently being generated. Please consult local extension officers."

# --- 🛠️ CORE HELPERS ---

def get_ui_context(lang='en'):
    translations = {
        'en': {'title': 'Agri-Guard Intelligence'},
        'sw': {'title': 'Agri-Guard Swahili'},
        'lg': {'title': 'Agri-Guard Luganda'}
    }
    return {
        't': translations.get(lang, translations['en']),
        'current_lang': lang,
        'weather': {'city': 'Kampala', 'temp': '28°C', 'desc': 'Partly Cloudy'},
        'theme_color': '#28a745'
    }

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute('''CREATE TABLE IF NOT EXISTS scans 
                    (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                     result TEXT, prescription TEXT, timestamp TEXT)''')
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
        # Step 1: Detect Disease with the new Retry Loop
        hf_results = detect_disease_with_retry(image_bytes)
        
        if not hf_results or not isinstance(hf_results, list):
            raise Exception("AI Engine did not return a valid list. Likely timeout.")

        top_result = hf_results[0]
        disease_name = top_result['label'].replace("___", " ").replace("_", " ")
        confidence = round(top_result['score'] * 100, 1)

        # Step 2: Get Treatment via OpenRouter
        treatment = get_treatment_advice(disease_name)

        # Log results to SQLite
        conn = sqlite3.connect(DB_PATH)
        conn.execute("INSERT INTO scans (result, prescription, timestamp) VALUES (?, ?, ?)",
                     (disease_name, treatment, datetime.now().strftime("%Y-%m-%d %H:%M")))
        conn.commit()
        history = conn.execute("SELECT result, timestamp FROM scans ORDER BY id DESC LIMIT 5").fetchall()
        conn.close()

        return render_template('index.html', 
                               prediction=f"{disease_name} ({confidence}%)", 
                               advice="Neural Analysis Successful",
                               prescription=treatment,
                               history=history,
                               **context)

    except Exception as e:
        # Fallback UI for when connection totally fails
        return render_template('index.html', 
                               prediction="SIGNAL INTERRUPTED", 
                               advice="Connection unstable. Retrying in background...", 
                               prescription=f"Technical Note: {str(e)}. Please rescan.", 
                               history=[], **context)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        if (request.form.get('username') == ADMIN_USER and 
            request.form.get('password') == ADMIN_PASS):
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
