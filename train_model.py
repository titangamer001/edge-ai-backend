import os
import pandas as pd
import numpy as np
from sklearn.ensemble import IsolationForest
import joblib
import time

MODEL_PATH = "isolation_forest.pkl"

def generate_training_data(num_samples=5000):
    print(f"[*] Generating {num_samples} telemetry samples for training...")
    
    # 95% Normal Data
    n_normal = int(num_samples * 0.95)
    normal_latency = np.random.normal(loc=15.0, scale=3.0, size=n_normal)
    normal_loss = np.abs(np.random.normal(loc=0.5, scale=0.5, size=n_normal))
    normal_bw = np.random.normal(loc=5.0, scale=1.0, size=n_normal)
    
    # 5% Anomalous Data (Spikes, Drops, DDoS)
    n_anom = num_samples - n_normal
    anom_latency = np.random.normal(loc=200.0, scale=50.0, size=n_anom)
    anom_loss = np.random.normal(loc=25.0, scale=10.0, size=n_anom)
    anom_bw = np.random.normal(loc=20.0, scale=5.0, size=n_anom)
    
    # Combine
    latency = np.concatenate([normal_latency, anom_latency])
    loss = np.concatenate([normal_loss, anom_loss])
    bw = np.concatenate([normal_bw, anom_bw])
    
    df = pd.DataFrame({
        'latency': latency,
        'packet_loss': loss,
        'bandwidth': bw
    })
    
    # Shuffle the dataset
    df = df.sample(frac=1, random_state=42).reset_index(drop=True)
    return df

def train():
    print("========================================")
    print("  EDGE AI ML MODEL TRAINING PIPELINE")
    print("========================================")
    
    df = generate_training_data(5000)
    print("\n[*] Training Data Profile:")
    print(df.describe())
    
    print("\n[*] Initializing Scikit-Learn Isolation Forest...")
    model = IsolationForest(
        n_estimators=150, 
        max_samples='auto', 
        contamination=0.05, 
        max_features=3, 
        random_state=42
    )
    
    print("[*] Training model on telemetry features (latency, packet_loss, bandwidth)...")
    start_time = time.time()
    
    # Train the model
    model.fit(df.values)
    
    print(f"[*] Training complete in {(time.time() - start_time):.2f} seconds.")
    
    # Save the model
    joblib.dump(model, MODEL_PATH)
    print(f"[*] Model successfully exported to: {os.path.abspath(MODEL_PATH)}")
    print("[*] The Edge AI backend will now use this model for real-time inference.")
    print("========================================")

if __name__ == "__main__":
    train()
