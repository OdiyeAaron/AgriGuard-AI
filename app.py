import os
import io
import sqlite3
import requests
import time
from flask import Flask, render_template, request, session, redirect, url_for, jsonify
from datetime import datetime, timedelta
from functools import wraps
from PIL import Image  # 🔥 Essential for compression

app = Flask(__name__)

# --- 🔐 CONFIG ---
app.secret_key = 'agri_guard_alpha_2026_st_lawrence'
app.permanent_session_lifetime = timedelta(minutes=60)

# Paths (Using /tmp for Render DB stability)
DB_PATH = '/tmp/agriguard.db'
os.makedirs(os.path.join(os.getcwd(), 'static', 'uploads'), exist_ok=True)

# Master Credentials
ADMIN_USER = "admin"
ADMIN_PASS = "StLawrence2026"

# --- 🔑 API KEYS ---
HF_TOKEN = os.getenv("HUGGINGFACE_API_KEY")
OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY")

# Model IDs
HF_MODEL_ID = "google/vit-base-patch16-224"
OR_MODEL_ID = "meta-llama/llama-3.1-8b-instruct:free"

# --- ⚡ STABILITY FUNCTIONS ---

def compress_image(image_file):
    """
    Reduces image size to 224x224. 
    This prevents 'IncompleteRead' errors by making the upload tiny.
    """
    img = Image.open(image_file)
    img = img.convert('RGB')
    img = img.resize((224, 224)) 
    
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=70) 
    return buffer.getvalue()

def detect_disease(image_bytes):
    """Sends image to Hugging Face with deep stability and JSON guards."""
    api_url = f"https://api-inference.huggingface.co/models/{HF_MODEL_ID}"
    headers = {
        "Authorization": f"Bearer {HF_TOKEN}",
        "X-Wait-For-Model": "true",
        "X-Use-Cache": "false"
    }
    
    for attempt in range(3):
        try:
            # stream=True ensures the data connection doesn't break prematurely
            response = requests.post(api_url, headers=headers, data=image_bytes, timeout=40, stream=True)
            
            if response.status_code != 200:
                print(f"API Attempt {attempt+1} failed: {response.status_code}")
                time.sleep(5)
                continue

            try:
                result = response.json()
            except ValueError:
                time.sleep(2)
                continue
            
            if isinstance(result, dict) and 'estimated_time' in result:
                wait_time = result.get('estimated_time', 12)
                time.sleep(min(wait_time, 12))
                continue
                
            return result

        except Exception as e:
            if attempt < 2:
                time.sleep(3)
                continue
            raise e
    return None

def get_treatment_advice(disease_name):
    """Gets localized treatment from OpenRouter."""
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENROUTER_KEY}",
        "Content-Type": "application/json"
    }
    
    prompt = (f"The crop is identified as '{disease_name}'. "
              "Provide 3 clear, organic treatment steps suitable for a farmer in South Sudan "
              "using local materials like wood ash or neem.")
    
    payload = {
        "model": OR_MODEL_ID,
        "messages": [{"role": "user", "content": prompt}]
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=25)
        return response.json()['choices'][0]['message']['content']
    except Exception:
        return "Apply organic mulch, maintain consistent watering, and consult a local agricultural officer."

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
        'weather': {'city': 'Kampala', 'temp': '28', 'desc': 'Sunny'},
        'theme_color': '#28a745'
    }

def init_db():
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute('''CREATE TABLE IF NOT EXISTS scans 
                        (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                         result TEXT, prescription TEXT, timestamp TEXT)''')
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"DB Error: {e}")

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
    
    try:
        # 🥇 NEW: Compress image before sending to AI
        image_bytes = compress_image(file)
        
        # Step 1: Detect
        hf_results = detect_disease(image_bytes)
        
        if not hf_results or not isinstance(hf_results, list):
            raise Exception("AI Engine is currently warming up.")

        top_result = hf_results[0]
        disease_label = top_result['label'].replace("_", " ").title()
        confidence = round(top_result['score'] * 100, 1)

        # Step 2: Treat
        treatment = get_treatment_advice(disease_label)

        # DB Log
        conn = sqlite3.connect(DB_PATH)
        conn.execute("INSERT INTO scans (result, prescription, timestamp) VALUES (?, ?, ?)",
                     (disease_label, treatment, datetime.now().strftime("%Y-%m-%d %H:%M")))
        conn.commit()
        history = conn.execute("SELECT result, timestamp FROM scans ORDER BY id DESC LIMIT 5").fetchall()
        conn.close()

        return render_template('index.html', 
                               prediction=f"{disease_label} ({confidence}%)", 
                               advice="Analysis Complete",
                               prescription=treatment,
                               history=history,
                               **context)

    except Exception as e:
        # 🥈 NEW: User-friendly error message (Hide technical jargon)
        return render_template('index.html', 
                               prediction="⚠️ PROCESSING INTERRUPTED", 
                               advice="The AI engine is currently busy.",
                               prescription="Please rescan. This is common when the neural engine is warming up.",
                               history=[],
                               **context)

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
