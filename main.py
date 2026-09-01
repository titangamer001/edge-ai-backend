import json
import asyncio
import threading
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
import paho.mqtt.client as mqtt

from database import SessionLocal, Device, Telemetry, Alert
from ml_engine import ai_engine
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
            # Register device
            device = db.query(Device).filter(Device.device_id == payload["id"]).first()
            if not device:
                device = Device(
                    device_id=payload["id"],
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
            
            # Predict
            score, is_anomaly = ai_engine.predict(lat, loss, bw)
            
            # Update Device health and status
            device = db.query(Device).filter(Device.device_id == device_id).first()
            if device:
                # Basic health calculation based on anomaly score and loss
                health = max(0, min(100, 100 - (score * 50) - (loss * 2)))
                device.health_score = health
                device.status = "online"
                db.commit()
            
            # Save telemetry
            record = Telemetry(
                device_id=device_id,
                latency=lat,
                packet_loss=loss,
                bandwidth=bw,
                anomaly_score=score,
                is_anomaly=int(is_anomaly)
            )
            db.add(record)
            
            # Handle Alerts internally
            if is_anomaly or lat > 200 or loss > 15:
                severity = "critical" if (lat > 250 or loss > 25) else "high"
                msg_text = f"Abnormal behavior detected on {device_id}. Latency: {lat:.1f}ms, Loss: {loss:.1f}%"
                alert = Alert(device_id=device_id, alert_type="Network Anomaly", severity=severity, message=msg_text, current_value=lat, threshold=200.0)
                db.add(alert)
                
                device_states[device_id] = "critical"
            else:
                if lat < 50 and loss < 5:
                    device_states[device_id] = "stable"
            
            # Aggregate State Machine (Only send 1 message for the whole network)
            active_criticals = [dev for dev, state in device_states.items() if state == "critical"]
            
            if len(active_criticals) > 0 and not getattr(app, "network_in_disaster", False):
                app.network_in_disaster = True
                try:
                    from notifier import trigger_external_alert
                    trigger_external_alert("MULTIPLE_NODES", "critical", f"Network disruption detected. Initial vector: {device_id}. Latency: {lat:.1f}ms, Loss: {loss:.1f}%")
                except ImportError:
                    pass
            elif len(active_criticals) == 0 and getattr(app, "network_in_disaster", False):
                app.network_in_disaster = False
                try:
                    from notifier import trigger_external_alert
                    trigger_external_alert("ALL_NODES", "stable", f"All network devices have successfully returned to normal telemetry baselines.")
                except ImportError:
                    pass
            
            db.commit()
            
            # Broadcast to UI
            payload["anomaly_score"] = float(score)
            payload["is_anomaly"] = bool(is_anomaly)
            payload["proxy_mode"] = False
            if device:
                payload["health_score"] = device.health_score
                
            asyncio.run_coroutine_threadsafe(manager.broadcast({"type": "telemetry", "data": payload}), uvicorn_loop)
            
            # Broadcast alerts if any
            if is_anomaly:
                alert_data = {
                    "device_id": device_id,
                    "severity": severity,
                    "message": msg_text,
                    "timestamp": payload["timestamp"]
                }
                asyncio.run_coroutine_threadsafe(manager.broadcast({"type": "alert", "data": alert_data}), uvicorn_loop)

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
                
                # Alert the frontend
                alert_data = {
                    "device_id": offline_dev,
                    "severity": "critical",
                    "message": msg_text,
                    "timestamp": payload["timestamp"]
                }
                asyncio.run_coroutine_threadsafe(manager.broadcast({"type": "alert", "data": alert_data}), uvicorn_loop)
                
                # Discord Webhook Notification
                try:
                    from notifier import trigger_external_alert
                    trigger_external_alert(offline_dev, "critical", msg_text)
                except:
                    pass

            # EDGE AI PROXY RECOVERY: Fetch last known good data for the offline device
            import time
            last_telemetry = db.query(Telemetry).filter(Telemetry.device_id == offline_dev).order_by(Telemetry.timestamp.desc()).first()
            if last_telemetry:
                proxy_payload = {
                    "device_id": offline_dev,
                    "latency": last_telemetry.latency,
                    "packet_loss": last_telemetry.packet_loss,
                    "bandwidth": last_telemetry.bandwidth,
                    "anomaly_score": last_telemetry.anomaly_score,
                    "is_anomaly": bool(last_telemetry.is_anomaly),
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
