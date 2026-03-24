import os
import io
import numpy as np
import tensorflow as tf
from PIL import Image
from flask import Flask, render_template, request, session, redirect, url_for, jsonify
import requests
from datetime import datetime, timedelta
from functools import wraps

app = Flask(__name__)
app.secret_key = 'agriguard_local_alpha_2026'
app.permanent_session_lifetime = timedelta(minutes=60)

# Paths
DB_PATH = '/tmp/agriguard.db'
os.makedirs(os.path.join(os.getcwd(), 'static', 'uploads'), exist_ok=True)

# Master Credentials
ADMIN_USER = "admin"
ADMIN_PASS = "StLawrence2026"

# --- 🧠 LOCAL AI SETUP (MobileNetV2) ---
# We load the model once when the app starts to save time
print("Loading Local Neural Engine...")
model = tf.keras.applications.MobileNetV2(weights='imagenet')

def predict_local(image_bytes):
    """Processes image locally using MobileNetV2 for instant results."""
    img = Image.open(io.BytesIO(image_bytes)).convert('RGB')
    img = img.resize((224, 224))
    
    # Preprocessing for MobileNetV2
    img_array = np.array(img)
    img_array = np.expand_dims(img_array, axis=0)
    img_array = tf.keras.applications.mobilenet_v2.preprocess_input(img_array)
    
    # Run Prediction
    predictions = model.predict(img_array)
    decoded = tf.keras.applications.mobilenet_v2.decode_predictions(predictions, top=1)[0]
    
    # Return (Label, Confidence Score)
    label = decoded[0][1].replace("_", " ").title()
    confidence = round(float(decoded[0][2]) * 100, 1)
    return label, confidence

# --- 🔑 EXTERNAL ADVICE (OpenRouter) ---
OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY")

def get_treatment_advice(disease_name):
    """Gets expert organic treatment via OpenRouter."""
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {"Authorization": f"Bearer {OPENROUTER_KEY}", "Content-Type": "application/json"}
    
    prompt = (f"The AI detected: '{disease_name}'. Provide 3 organic treatment steps "
              "suitable for a farmer in South Sudan using local materials like neem or wood ash.")
    
    try:
        res = requests.post(url, headers=headers, json={
            "model": "meta-llama/llama-3.1-8b-instruct:free",
            "messages": [{"role": "user", "content": prompt}]
        }, timeout=15)
        return res.json()['choices'][0]['message']['content']
    except:
        return "Ensure proper soil drainage and apply organic compost to strengthen the plant."

# --- 🛠️ HELPERS & AUTH ---

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
    # Basic UI Context
    context = {
        't': {'title': 'Agri-Guard Intelligence'},
        'weather': {'city': 'Kampala', 'temp': '28', 'desc': 'Sunny'},
        'current_lang': 'en'
    }
    return render_template('index.html', **context)

@app.route('/predict', methods=['POST'])
@login_required
def predict():
    file = request.files.get('file')
    if not file: return redirect(url_for('index'))

    try:
        image_bytes = file.read()
        
        # 🥇 STEP 1: Instant Local Prediction
        label, confidence = predict_local(image_bytes)
        
        # 🥈 STEP 2: Cloud-Based Treatment Advice
        treatment = get_treatment_advice(label)

        return render_template('index.html', 
                               prediction=f"{label} ({confidence}%)", 
                               advice="LOCAL NEURAL ENGINE ANALYSIS COMPLETE",
                               prescription=treatment,
                               t={'title': 'Agri-Guard AI'},
                               weather={'city': 'Kampala', 'temp': '28', 'desc': 'Sunny'})

    except Exception as e:
        print(f"Error: {e}")
        return render_template('index.html', 
                               prediction="⚠️ SENSOR ERROR", 
                               advice="Local analysis failed.",
                               prescription="Ensure the image is clear and try again.",
                               t={'title': 'Agri-Guard AI'},
                               weather={'city': 'Kampala', 'temp': '28', 'desc': 'Cloudy'})

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        if request.form.get('username') == ADMIN_USER and request.form.get('password') == ADMIN_PASS:
            session['logged_in'] = True
            return redirect(url_for('index'))
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
