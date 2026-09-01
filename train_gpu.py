import time
import torch
import torch.nn as nn
import torch.optim as optim
from sklearn.datasets import fetch_kddcup99
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
import numpy as np
import joblib

print("="*60)
print(" EDGE AI - GPU AUTOENCODER TRAINING (KDD CUP 99)")
print("="*60)

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
print(f"[*] Target Compute Device: {device.type.upper()}")
if device.type == "cuda":
    print(f"[*] GPU Model: {torch.cuda.get_device_name(0)}")

print("[*] Downloading Kaggle/UCI KDDCup99 dataset subset (HTTP)...")
# fetch_kddcup99 subset='http' contains 3 features: duration, src_bytes, dst_bytes
kdd = fetch_kddcup99(subset='http', percent10=True)
X = kdd.data.astype(np.float32)

print(f"[*] Fetched {X.shape[0]} samples with {X.shape[1]} features.")

scaler = StandardScaler()
X_scaled = scaler.fit_transform(X)

X_train, X_test = train_test_split(X_scaled, test_size=0.2, random_state=42)

train_tensor = torch.tensor(X_train).to(device)
test_tensor = torch.tensor(X_test).to(device)

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

input_dim = X.shape[1]
model = AnomalyAutoencoder(input_dim).to(device)
criterion = nn.MSELoss()
optimizer = optim.Adam(model.parameters(), lr=0.001)

epochs = 10
batch_size = 512

print(f"[*] Starting model training on {device.type.upper()}...")
start_time = time.time()

for epoch in range(epochs):
    model.train()
    permutation = torch.randperm(train_tensor.size()[0])
    epoch_loss = 0
    for i in range(0, train_tensor.size()[0], batch_size):
        indices = permutation[i:i+batch_size]
        batch_x = train_tensor[indices]
        
        optimizer.zero_grad()
        outputs = model(batch_x)
        loss = criterion(outputs, batch_x)
        loss.backward()
        optimizer.step()
        
        epoch_loss += loss.item()
        
    print(f"    Epoch {epoch+1:02d}/{epochs} | Loss: {epoch_loss/len(train_tensor):.6f}")

print(f"[*] Training completed in {time.time() - start_time:.2f} seconds.")

torch.save(model.state_dict(), "autoencoder.pth")
joblib.dump(scaler, "autoencoder_scaler.pkl")
print("[*] Deep Learning Model exported to 'autoencoder.pth'")
print("============================================================")
