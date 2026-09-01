import pandas as pd
import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
import joblib
import time

print("="*60)
print(" EDGE AI - GPU AUTOENCODER TRAINING (UNSW-NB15)")
print("="*60)

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
print(f"[*] Target Compute Device: {device.type.upper()}")

print("[*] Loading Kaggle UNSW-NB15 dataset partition 1 (168MB)...")
df = pd.read_csv('UNSW-NB15_1.csv', header=None, low_memory=False)

# Grab 3 numeric features (Cols 6, 7, 8) to act as our telemetry proxies
X = df.iloc[:, [6, 7, 8]].apply(pd.to_numeric, errors='coerce').fillna(0).values.astype(np.float32)

print(f"[*] Fetched {X.shape[0]} real network intrusion samples.")

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
        return self.decoder(self.encoder(x))

model = AnomalyAutoencoder(X.shape[1]).to(device)
criterion = nn.MSELoss()
optimizer = optim.Adam(model.parameters(), lr=0.001)

epochs = 5
batch_size = 1024

print(f"[*] Starting deep learning training on {device.type.upper()}...")
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
