import os
import sqlite3
import google.generativeai as genai
from flask import Flask, render_template, request, session, redirect, url_for, jsonify
from datetime import datetime, timedelta
from functools import wraps

app = Flask(__name__)

# --- 🔐 CONFIG ---
app.secret_key = 'agri_guard_alpha_2026_st_lawrence'
app.permanent_session_lifetime = timedelta(minutes=60)

# Paths - Using /tmp for Render DB stability
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads')
DB_PATH = '/tmp/agriguard.db'

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Master Credentials for Aaron Awas Alpha
ADMIN_USER = "admin"
ADMIN_PASS = "StLawrence2026"

# --- 🤖 GEMINI AI CONFIG ---
GEMINI_KEY = os.getenv("GEMINI_API_KEY")
if GEMINI_KEY:
    genai.configure(api_key=GEMINI_KEY)
    model = genai.GenerativeModel('gemini-1.5-flash')

# --- 🛠️ UI DATA HELPERS ---
def get_ui_context(lang='en'):
    """Provides the 't' and 'weather' variables your index.html needs."""
    translations = {
        'en': {'title': 'Agri-Guard AI'},
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
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute('''CREATE TABLE IF NOT EXISTS scans 
                        (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                         filename TEXT, result TEXT, advice TEXT, 
                         prescription TEXT, timestamp TEXT)''')
        conn.commit()
        conn.close()
        print(f"✅ DB initialized at {DB_PATH}")
    except Exception as e:
        print(f"DB Error: {e}")

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
    context = get_ui_context(lang)
    
    try:
        conn = sqlite3.connect(DB_PATH)
        history = conn.execute("SELECT result, timestamp FROM scans ORDER BY id DESC LIMIT 5").fetchall()
        conn.close()
    except:
        history = []
        
    return render_template('index.html', history=history, **context)

@app.route('/predict', methods=['POST'])
@login_required
def predict():
    lang = request.form.get('lang', 'en')
    context = get_ui_context(lang)
    
    file = request.files.get('file')
    if not file or file.filename == '':
        return redirect(url_for('index'))

    filename = datetime.now().strftime("%Y%m%d_%H%M%S_") + file.filename
    save_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(save_path)

    try:
        with open(save_path, "rb") as f:
            image_bytes = f.read()
        
        # Expert AI Prompt
        prompt = """Analyze this agricultural image. 
        1. Identify if it's a LEAF or SEED. 
        2. Determine if it's HEALTHY or DISEASED. 
        3. Provide 3 specific organic/chemical treatment steps."""
        
        response = model.generate_content([prompt, {'mime_type': 'image/jpeg', 'data': image_bytes}])
        analysis_text = response.text
        
        status_label = "HEALTHY" if "HEALTHY" in analysis_text.upper() else "DISEASE DETECTED"

        # Save result to DB
        conn = sqlite3.connect(DB_PATH)
        conn.execute("INSERT INTO scans (filename, result, advice, prescription, timestamp) VALUES (?, ?, ?, ?, ?)",
                     (filename, status_label, "Neural Engine Analysis", analysis_text, datetime.now().strftime("%Y-%m-%d %H:%M")))
        conn.commit()
        history = conn.execute("SELECT result, timestamp FROM scans ORDER BY id DESC LIMIT 5").fetchall()
        conn.close()

        return render_template('index.html', 
                               prediction=status_label, 
                               advice="Biometric scan complete. Neural patterns decoded.",
                               prescription=analysis_text, 
                               image_path=url_for('static', filename='uploads/'+filename), 
                               history=history,
                               **context)
    except Exception as e:
        print(f"Prediction Error: {e}")
        return f"System Error: {e}", 500

@app.route('/analytics_data')
@login_required
def analytics_data():
    """Powers the Chart.js doughnut chart in your UI."""
    return jsonify({
        "labels": ["Healthy Samples", "Infected", "Molds"],
        "values": [12, 5, 3]
    })

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        u = (request.form.get('username') or '').lower().strip()
        p = (request.form.get('password') or '').strip()
        
        if u == ADMIN_USER and p == ADMIN_PASS:
            session.permanent = True
            session['logged_in'] = True
            init_db() # Ensure DB is ready in /tmp/
            return redirect(url_for('index'))
            
        return render_template('login.html', error="Invalid Credentials")
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    # Initialize DB before server starts
    init_db()
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
