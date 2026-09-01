import os
import joblib
import numpy as np
import torch
import torch.nn as nn
from sklearn.ensemble import IsolationForest

MODEL_PATH_IF = "isolation_forest.pkl"
MODEL_PATH_DL = "autoencoder.pth"
SCALER_PATH = "autoencoder_scaler.pkl"

class AnomalyAutoencoder(nn.Module):
    def __init__(self, input_dim):
        super(AnomalyAutoencoder, self).__init__()
        self.encoder = nn.Sequential(
            nn.Linear(input_dim, 8),
            nn.ReLU(),
            nn.Linear(8, 2)
        )
        self.decoder = nn.Sequential(
            nn.Linear(2, 8),
            nn.ReLU(),
            nn.Linear(8, input_dim)
        )

    def forward(self, x):
        encoded = self.encoder(x)
        decoded = self.decoder(encoded)
        return decoded

class AnomalyDetector:
    def __init__(self):
        self.model = None
        self.scaler = None
        self.is_ready = False
        self.mode = "none"
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self._initialize_model()

    def _initialize_model(self):
        if os.path.exists(MODEL_PATH_DL) and os.path.exists(SCALER_PATH):
            try:
                print(f"[*] Loading PyTorch Deep Learning Model on {self.device}...")
                self.scaler = joblib.load(SCALER_PATH)
                self.model = AnomalyAutoencoder(3).to(self.device)
                self.model.load_state_dict(torch.load(MODEL_PATH_DL, map_location=self.device))
                self.model.eval()
                self.is_ready = True
                self.mode = "dl"
                print("[*] PyTorch Autoencoder Ready.")
            except Exception as e:
                print(f"Error loading DL model: {e}")
                self._load_if()
        else:
            self._load_if()

    def _load_if(self):
        if os.path.exists(MODEL_PATH_IF):
            self.model = joblib.load(MODEL_PATH_IF)
            self.is_ready = True
            self.mode = "if"
            print("[*] Scikit-Learn Isolation Forest Ready.")
        else:
            self.is_ready = False

    def predict(self, latency, packet_loss, bandwidth):
        if not self.is_ready:
            return 0.0, False
            
        if self.mode == "dl":
            X = np.array([[latency, packet_loss, bandwidth]], dtype=np.float32)
            X_scaled = self.scaler.transform(X)
            tensor_X = torch.tensor(X_scaled).to(self.device)
            with torch.no_grad():
                reconstructed = self.model(tensor_X)
                loss = torch.nn.functional.mse_loss(reconstructed, tensor_X).item()
                
            # Normalize reconstruction loss to an anomaly score (0 to 1)
            # Typically losses > 0.5 mean anomaly in this scaled context
            normalized_score = min(1.0, loss * 2.0)
            is_anomaly = bool(normalized_score > 0.7)
            return normalized_score, is_anomaly
            
        elif self.mode == "if":
            X = np.array([[latency, packet_loss, bandwidth]])
            score = self.model.decision_function(X)[0]
            normalized_score = max(0.0, min(1.0, 0.5 - score * 2.0))
            is_anomaly = bool(self.model.predict(X)[0] == -1)
            return normalized_score, is_anomaly

ai_engine = AnomalyDetector()
