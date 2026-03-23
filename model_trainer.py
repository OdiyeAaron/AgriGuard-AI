import pandas as pd
import numpy as np
import xgboost as xgb
import joblib
import os
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score

# Ensure the model directory exists
os.makedirs('models', exist_ok=True)

print("📂 Generating 10-Feature Dataset (High-Accuracy Version)...")

np.random.seed(42)
n_samples = 1000 # Samples per category

def create_samples(green, brown, mold, edges, texture, objects, red, yellow, sym, cont, label):
    return pd.DataFrame({
        'green': np.random.uniform(*green, n_samples),
        'brown': np.random.uniform(*brown, n_samples),
        'mold': np.random.uniform(*mold, n_samples),
        'edges': np.random.uniform(*edges, n_samples),
        'texture': np.random.uniform(*texture, n_samples),
        'objects': np.random.uniform(*objects, n_samples),
        'red_intensity': np.random.uniform(*red, n_samples),
        'yellowing': np.random.uniform(*yellow, n_samples),
        'symmetry': np.random.uniform(*sym, n_samples),
        'contrast': np.random.uniform(*cont, n_samples),
        'label': np.full(n_samples, label)
    })

# --- DATASET DEFINITIONS ---

# 1: HEALTHY LEAF (High green, high symmetry)
df_healthy_leaf = create_samples(
    (60, 95), (0, 10), (0, 5), (5, 20), (20, 60), (1, 5), 
    (0, 5), (0, 10), (75, 98), (30, 60), 1
)

# 3: HEALTHY BEANS (Natural red spots, high contrast, high symmetry)
df_healthy_seeds = create_samples(
    (0, 5), (10, 40), (0, 10), (20, 60), (40, 80), (15, 95), 
    (40, 95), (0, 5), (65, 95), (70, 100), 3
)

# 0: DISEASED (Low symmetry, high mold/yellowing, fuzzy contrast)
df_diseased = create_samples(
    (5, 35), (35, 85), (25, 75), (30, 90), (60, 100), (5, 30), 
    (5, 30), (45, 95), (10, 45), (15, 55), 0
)

# 2: INVALID/OBJECTS (Walls, floors, clothes - very low texture/symmetry)
df_invalid = create_samples(
    (0, 100), (0, 100), (0, 100), (0, 10), (0, 15), (0, 5), 
    (0, 100), (0, 100), (0, 25), (0, 30), 2
)

# Combine and Shuffle
df = pd.concat([df_healthy_leaf, df_healthy_seeds, df_diseased, df_invalid]).sample(frac=1).reset_index(drop=True)

X = df.drop('label', axis=1)
y = df['label']

X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, stratify=y)

print("🤖 Training 10-Feature XGBoost Brain...")
model = xgb.XGBClassifier(
    n_estimators=150, 
    max_depth=6, 
    learning_rate=0.1, 
    objective='multi:softprob'
)

model.fit(X_train, y_train)

acc = accuracy_score(y_test, model.predict(X_test))
print(f"✅ Training Accuracy: {acc * 100:.2f}%")

# Save the model
joblib.dump(model, 'models/leaf_model.pkl')
print("💾 Saved Updated Model: models/leaf_model.pkl")