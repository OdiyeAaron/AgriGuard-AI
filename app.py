import os
import io
import sqlite3
import requests
import time
import replicate  # 🔥 New official SDK
from flask import Flask, render_template, request, session, redirect, url_for, jsonify
from datetime import datetime, timedelta
from functools import wraps
from PIL import Image

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

# --- 🔑 API KEYS ---
# Ensure REPLICATE_API_TOKEN is added to Render Environment Variables
REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN")
OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY")

# Model IDs
# Using BLIP - a highly stable Vision-to-Text model
REPLICATE_MODEL = "salesforce/blip:2e1eb2c119a08990e39ff878196e838e4a5d3c52f6d4d444452219717651a027"
OR_MODEL_ID = "meta-llama/llama-3.1-8b-instruct:free"

# --- ⚡ STABILITY FUNCTIONS ---

def compress_image(image_file):
    """Reduces image size for faster cloud processing."""
    img = Image.open(image_file)
    img = img.convert('RGB')
    img = img.resize((400, 400)) # Replicate handles slightly larger images better
    
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=75) 
    buffer.seek(0)
    return buffer

def detect_disease_replicate(image_buffer):
    """Uses Replicate SDK for a stable connection."""
    try:
        output = replicate.run(
            REPLICATE_MODEL,
            input={
                "image": image_buffer,
                "task": "image_captioning",
                "question": "Identify the specific crop disease or health status of this plant leaf."
            }
        )
        return str(output).replace("caption: ", "")
    except Exception as e:
        print(f"Replicate Error: {e}")
        return None

def get_treatment_advice(analysis_text):
    """Gets organic treatment via OpenRouter."""
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {"Authorization": f"Bearer {OPENROUTER_KEY}", "Content-Type": "application/json"}
    
    prompt = (f"The AI detected: '{analysis_text}'. "
              "If this is a disease, provide 3 clear, organic treatment steps for a farmer in South Sudan. "
              "If the leaf is healthy, give 1 maintenance tip.")
    
    payload = {
        "model": OR_MODEL_ID,
        "messages": [{"role": "user", "content": prompt}]
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=25)
        return response.json()['choices'][0]['message']['content']
    except Exception:
        return "Apply organic mulch and ensure proper spacing between crops."

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
        # Step 1: Compress
        image_buffer = compress_image(file)
        
        # Step 2: Detect via Replicate
        analysis = detect_disease_replicate(image_buffer)
        
        if not analysis:
            raise Exception("AI Cloud recalibrating.")

        # Step 3: Treatment
        treatment = get_treatment_advice(analysis)

        # DB Log
        conn = sqlite3.connect(DB_PATH)
        conn.execute("INSERT INTO scans (result, prescription, timestamp) VALUES (?, ?, ?)",
                     (analysis.title(), treatment, datetime.now().strftime("%Y-%m-%d %H:%M")))
        conn.commit()
        history = conn.execute("SELECT result, timestamp FROM scans ORDER BY id DESC LIMIT 5").fetchall()
        conn.close()

        return render_template('index.html', 
                               prediction=analysis.upper(), 
                               advice="REPLICATE ENGINE ANALYSIS COMPLETE",
                               prescription=treatment,
                               history=history,
                               **context)

    except Exception as e:
        return render_template('index.html', 
                               prediction="⚠️ PROCESSING INTERRUPTED", 
                               advice="The AI engine is currently busy.",
                               prescription="Please rescan the leaf to establish a fresh neural link.",
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
