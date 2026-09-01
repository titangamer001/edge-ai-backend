import json
import asyncio
import threading
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
import paho.mqtt.client as mqtt

from database import SessionLocal, Device, Telemetry, Alert, User
from simulator import simulator_engine, UNIQUE_ID
MQTT_BROKER = "test.mosquitto.org"
MQTT_PORT = 1883
MQTT_TOPIC = "edge_ai/telemetry/+"

app = FastAPI(title="Edge AI Network Management Platform API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        #print(f"Broadcasting to {len(self.active_connections)} connections")
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                print(f"Broadcast error: {e}")

manager = ConnectionManager()
uvicorn_loop = None

mqtt_client = mqtt.Client()

import time
try:
    from notifier import trigger_external_alert
except ImportError:
    def trigger_external_alert(*args, **kwargs): pass

async def db_pruner():
    """Background task to delete telemetry data older than 2 hours to prevent database bloat."""
    while True:
        try:
            await asyncio.sleep(300) # Run every 5 minutes
            db = SessionLocal()
            try:
                cutoff = time.time() - (2 * 3600) # 2 hours ago
                deleted = db.query(Telemetry).filter(Telemetry.timestamp < cutoff).delete()
                db.commit()
                if deleted > 0:
                    print(f"[*] DB Pruner: Cleaned up {deleted} old telemetry records.")
            except Exception as e:
                print(f"[*] DB Pruner Error: {e}")
            finally:
                db.close()
        except asyncio.CancelledError:
            break

def on_connect(client, userdata, flags, rc):
    print("API connected to MQTT Broker")
    client.subscribe(f"{UNIQUE_ID}/devices/register")
    client.subscribe(f"{UNIQUE_ID}/telemetry/+")
    client.subscribe(f"{UNIQUE_ID}/peer_alert/+")

device_states = {} # Tracks global alert states

def on_message(client, userdata, msg):
    print(f"MQTT Recv: {msg.topic}")
    topic = msg.topic
    payload = json.loads(msg.payload.decode())
    db = SessionLocal()
    try:
        if topic.endswith("/register"):
            device_id = payload["id"]
            device = db.query(Device).filter(Device.device_id == device_id).first()
            if not device:
                device = Device(
                    device_id=device_id,
                    name=payload["name"],
                    location=payload["location"],
                    device_type=payload["type"]
                )
                db.add(device)
                db.commit()
        elif "/telemetry/" in topic:
            device_id = payload["device_id"]
            lat = payload["latency"]
            loss = payload["packet_loss"]
            bw = payload["bandwidth"]
            
            # Update Node Health Status without AI
            device = db.query(Device).filter(Device.device_id == device_id).first()
            if device:
                # Basic health calculation based on latency and loss directly
                health = max(0, min(100, 100 - (lat / 5.0) - (loss * 2)))
                device.health_score = health
                device.status = "online"
                db.commit()
            
            # Save telemetry
            record = Telemetry(
                device_id=device_id,
                latency=lat,
                packet_loss=loss,
                bandwidth=bw
            )
            db.add(record)
            
            # Handle Alerts internally (Edge-Triggered)
            # Prioritize physical stability bounds over AI noise to ensure recovery triggers correctly
            if lat < 50 and loss < 5:
                device_states[device_id] = "stable"
            elif lat > 200 or loss > 15:
                if device_states.get(device_id) != "critical":
                    device_states[device_id] = "critical"
            
            # Aggregate State Machine (Only send 1 message for the whole network)
            active_criticals = [dev for dev, state in device_states.items() if state == "critical"]
            
            if len(active_criticals) > 0 and not getattr(app, "network_in_disaster", False):
                print(f"[*] STATE TRIGGER: network_in_disaster = True ({len(active_criticals)} criticals)")
                app.network_in_disaster = True
                msg = f"Network disruption detected! Vector: {device_id}."
                
                print("Adding alert to db")
                alert = Alert(device_id="SYSTEM", alert_type="Network Anomaly", severity="critical", message=msg, current_value=lat, threshold=200.0)
                db.add(alert)
                
                alert_data = {
                    "device_id": "SYSTEM",
                    "severity": "critical",
                    "message": msg,
                    "timestamp": payload["timestamp"]
                }
                print("Broadcasting to UI")
                asyncio.run_coroutine_threadsafe(manager.broadcast({"type": "alert", "data": alert_data}), uvicorn_loop)
                print("Broadcast queued")
                
                try:
                    trigger_external_alert("MULTIPLE_NODES", "critical", msg, loop=uvicorn_loop)
                    print("Triggered external alert")
                except Exception as e:
                    print(f"Failed external alert: {e}")
            elif len(active_criticals) == 0 and getattr(app, "network_in_disaster", False):
                print("[*] STATE TRIGGER: network_in_disaster = False (0 criticals, recovering)")
                app.network_in_disaster = False
                msg = "All network devices have returned to normal stable baselines."
                
                print("Adding alert to db")
                alert = Alert(device_id="SYSTEM", alert_type="Recovery", severity="info", message=msg, current_value=lat, threshold=50.0)
                db.add(alert)
                
                alert_data = {
                    "device_id": "SYSTEM",
                    "severity": "info",
                    "message": msg,
                    "timestamp": payload["timestamp"]
                }
                asyncio.run_coroutine_threadsafe(manager.broadcast({"type": "alert", "data": alert_data}), uvicorn_loop)
                
                try:
                    trigger_external_alert("ALL_NODES", "stable", msg, loop=uvicorn_loop)
                except Exception:
                    pass
            
            print("Committing DB")
            db.commit()
            print("DB Committed")
            
            # Broadcast to UI
            payload["proxy_mode"] = False
            if device:
                payload["health_score"] = device.health_score
                
            asyncio.run_coroutine_threadsafe(manager.broadcast({"type": "telemetry", "data": payload}), uvicorn_loop)

        elif "/peer_alert/" in topic:
            offline_dev = payload["offline_neighbor"]
            reporter = payload["reporter"]
            
            # Update Device Status to offline
            device = db.query(Device).filter(Device.device_id == offline_dev).first()
            if device and device.status != "offline":
                device.status = "offline"
                
                # Create an alert for P2P failure
                msg_text = f"P2P Alert: {reporter} lost contact with neighbor {offline_dev}."
                alert = Alert(device_id=offline_dev, alert_type="Peer Failure", severity="critical", message=msg_text, current_value=0, threshold=0)
                db.add(alert)
                db.commit()
                
                # Alert the frontend (always)
                alert_data = {
                    "device_id": offline_dev,
                    "severity": "critical",
                    "message": msg_text,
                    "timestamp": payload["timestamp"]
                }
                asyncio.run_coroutine_threadsafe(manager.broadcast({"type": "alert", "data": alert_data}), uvicorn_loop)

            # EDGE AI PROXY RECOVERY: Fetch last known good data for the offline device
            last_telemetry = db.query(Telemetry).filter(Telemetry.device_id == offline_dev).order_by(Telemetry.timestamp.desc()).first()
            if last_telemetry:
                proxy_payload = {
                    "device_id": offline_dev,
                    "latency": last_telemetry.latency,
                    "packet_loss": last_telemetry.packet_loss,
                    "bandwidth": last_telemetry.bandwidth,
                    "timestamp": time.time(),
                    "proxy_mode": True,
                    "reporter": reporter,
                    "health_score": device.health_score if device else 0
                }
                asyncio.run_coroutine_threadsafe(manager.broadcast({"type": "telemetry", "data": proxy_payload}), uvicorn_loop)

                
    except Exception as e:
        print(f"Error processing MQTT message: {e}")
    finally:
        db.close()

mqtt_client.on_connect = on_connect
mqtt_client.on_message = on_message

@app.on_event("startup")
def startup():
    global uvicorn_loop
    uvicorn_loop = asyncio.get_running_loop()
    uvicorn_loop.create_task(db_pruner())
    
    # Start Discord Bot
    try:
        from notifier import start_discord_bot
        uvicorn_loop.create_task(start_discord_bot())
    except Exception as e:
        print(f"[MAIN] Failed to initialize Discord Bot: {e}")
        
    # Start MQTT Client
    mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
    threading.Thread(target=mqtt_client.loop_forever, daemon=True).start()
    
    # Start Simulator
    threading.Thread(target=simulator_engine.run, daemon=True).start()

@app.websocket("/ws/stream")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)

@app.get("/api/devices")
def get_devices():
    db = SessionLocal()
    devices = db.query(Device).all()
    db.close()
    return devices

@app.get("/api/alerts")
def get_alerts():
    db = SessionLocal()
    alerts = db.query(Alert).order_by(Alert.timestamp.desc()).limit(50).all()
    db.close()
    return alerts

@app.post("/api/simulation/disaster/{action}")
def trigger_disaster(action: str):
    if action == "none" or action == "clear":
        simulator_engine.set_disaster_mode(False)
        return {"status": "Disaster mode deactivated. Network normalizing."}
    
    simulator_engine.set_disaster_mode(True, action)
    return {"status": f"Disaster mode activated: {action}"}

@app.post("/api/simulation/pause")
def pause_simulation():
    simulator_engine.paused = True
    return {"status": "Network simulation stopped."}

@app.post("/api/simulation/resume")
def resume_simulation():
    simulator_engine.paused = False
    return {"status": "Network simulation resumed."}
import os
from dotenv import load_dotenv
load_dotenv()
import jwt
import requests
from urllib.parse import urlencode
from fastapi import Body, HTTPException

JWT_SECRET = os.getenv("JWT_SECRET", "super-secret-edge-ai-key")
DISCORD_CLIENT_ID = os.getenv("DISCORD_CLIENT_ID", "")
DISCORD_CLIENT_SECRET = os.getenv("DISCORD_CLIENT_SECRET", "")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")
REDIRECT_URI = f"{FRONTEND_URL}/auth/callback"

@app.get("/api/auth/discord/url")
def get_discord_auth_url():
    params = {
        "client_id": DISCORD_CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": "identify guilds.join",
    }
    url = f"https://discord.com/api/oauth2/authorize?{urlencode(params)}"
    return {"url": url}

@app.post("/api/auth/discord/callback")
def discord_callback(payload: dict = Body(...)):
    code = payload.get("code")
    data = {
        "client_id": DISCORD_CLIENT_ID,
        "client_secret": DISCORD_CLIENT_SECRET,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    r = requests.post("https://discord.com/api/oauth2/token", data=data, headers=headers)
    if r.status_code != 200:
        raise HTTPException(status_code=400, detail="Invalid code")
    
    tokens = r.json()
    access_token = tokens["access_token"]
    
    user_r = requests.get("https://discord.com/api/users/@me", headers={"Authorization": f"Bearer {access_token}"})
    if user_r.status_code != 200:
        raise HTTPException(status_code=400, detail="Failed to fetch user")
        

    user_data = user_r.json()
    discord_id = str(user_data["id"])
    username = user_data.get("username")
    avatar_hash = user_data.get("avatar")
    avatar_url = f"https://cdn.discordapp.com/avatars/{discord_id}/{avatar_hash}.png" if avatar_hash else None
    
    db = SessionLocal()
    import datetime
    try:
        db_user = db.query(User).filter(User.discord_id == discord_id).first()
        if not db_user:
            db_user = User(
                discord_id=discord_id,
                username=username,
                avatar_url=avatar_url,
                last_login=datetime.datetime.utcnow()
            )
            db.add(db_user)
        else:
            db_user.username = username
            db_user.avatar_url = avatar_url
            db_user.last_login = datetime.datetime.utcnow()
        db.commit()
    finally:
        db.close()

    
    # Trigger auto-role assignment
    from notifier import trigger_auto_role
    try:
        trigger_auto_role(discord_id, loop=uvicorn_loop)
    except Exception as e:
        print(f"Auto-role trigger failed: {e}")
    
    token = jwt.encode({"sub": discord_id, "name": user_data.get("username")}, JWT_SECRET, algorithm="HS256")
    return {"token": token, "user": user_data}
