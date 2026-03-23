import os
import sqlite3
import google.generativeai as genai
from flask import Flask, render_template, request, session, redirect, url_for
from datetime import datetime, timedelta
from functools import wraps

app = Flask(__name__)

# --- 🔐 CONFIG ---
app.secret_key = 'agri_guard_alpha_2026_st_lawrence'
app.permanent_session_lifetime = timedelta(minutes=60)

# Render-safe Absolute Paths
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads')
DB_PATH = os.path.join(BASE_DIR, 'agriguard.db')

# Ensure folders exist physically on the server
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Master Credentials for Presentation
ADMIN_USER = "admin"
ADMIN_PASS = "StLawrence2026"

# --- 🤖 GEMINI AI CONFIG ---
# This pulls the key you set in the Render 'Environment' tab
GEMINI_KEY = os.getenv("GEMINI_API_KEY")
if GEMINI_KEY:
    genai.configure(api_key=GEMINI_KEY)
    model = genai.GenerativeModel('gemini-1.5-flash')
else:
    print("⚠️ CRITICAL ERROR: GEMINI_API_KEY is missing from Render settings!")

# --- 🛡️ UTILITIES ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def init_db():
    """Creates the database file and table if they don't exist."""
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute('''CREATE TABLE IF NOT EXISTS scans 
                        (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                         filename TEXT, 
                         result TEXT, 
                         advice TEXT, 
                         prescription TEXT, 
                         timestamp TEXT)''')
        conn.commit()
        conn.close()
        print(f"✅ Database initialized at {DB_PATH}")
    except Exception as e:
        print(f"❌ Database Error: {e}")

# Initialize DB on app startup
init_db()

# --- 🚀 ROUTES ---

@app.route('/')
@login_required
def index():
    # Fetch recent history for the dashboard
    try:
        conn = sqlite3.connect(DB_PATH)
        history = conn.execute("SELECT result, timestamp FROM scans ORDER BY id DESC LIMIT 5").fetchall()
        conn.close()
    except:
        history = []
    return render_template('index.html', history=history)

@app.route('/predict', methods=['POST'])
@login_required
def predict():
    file = request.files.get('file')
    if not file or file.filename == '':
        return redirect(url_for('index'))

    # Save the file locally
    filename = datetime.now().strftime("%Y%m%d_%H%M%S_") + file.filename
    save_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(save_path)

    try:
        # 1. Read image bytes for Gemini
        with open(save_path, "rb") as f:
            image_bytes = f.read()
        
        # 2. AI Instructions
        prompt = """
        Analyze this agricultural image. 
        1. Identify if it is a LEAF or SEED.
        2. Determine if it is HEALTHY or DISEASED.
        3. Provide 3 specific treatment steps.
        
        Format your response as:
        STATUS: [Healthy/Diseased/Invalid]
        DETAILS: [Description]
        PRESCRIPTION: [Bullet points]
        """
        
        # 3. Call Gemini Vision API
        response = model.generate_content([
            prompt, 
            {'mime_type': 'image/jpeg', 'data': image_bytes}
        ])
        
        analysis_text = response.text

        # 4. Set UI Status Label
        status_label = "ANALYSIS COMPLETE"
        if "HEALTHY" in analysis_text.upper(): 
            status_label = "HEALTHY"
        elif "DISEASE" in analysis_text.upper() or "SICK" in analysis_text.upper(): 
            status_label = "DISEASE DETECTED"

        # 5. Log results to SQLite
        conn = sqlite3.connect(DB_PATH)
        conn.execute("INSERT INTO scans (filename, result, advice, prescription, timestamp) VALUES (?, ?, ?, ?, ?)",
                     (filename, status_label, "AI Vision Analysis", analysis_text, datetime.now().strftime("%Y-%m-%d %H:%M")))
        conn.commit()
        history = conn.execute("SELECT result, timestamp FROM scans ORDER BY id DESC LIMIT 5").fetchall()
        conn.close()

        return render_template('index.html', 
                               prediction=status_label, 
                               prescription=analysis_text, 
                               image_path=url_for('static', filename='uploads/'+filename), 
                               history=history)
    
    except Exception as e:
        print(f"Prediction Error: {e}")
        return f"AI Analysis Failed: {e}", 500

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        # Safely capture form data
        u = (request.form.get('username') or '').lower().strip()
        p = (request.form.get('password') or '').strip()
        
        # presentation login credentials
        if u == ADMIN_USER and p == ADMIN_PASS:
            session.permanent = True
            session['logged_in'] = True
            session['username'] = ADMIN_USER
            init_db() # Ensure DB is ready on login
            return redirect(url_for('index'))
            
        return render_template('login.html', error="Invalid Credentials")
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    # Use Render's assigned port or default to 5000
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
