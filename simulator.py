import time
import json
import random
import threading
import uuid
import paho.mqtt.client as mqtt

MQTT_BROKER = "test.mosquitto.org"
MQTT_PORT = 1883
UNIQUE_ID = f"edgeai_sim_{uuid.uuid4().hex[:8]}"

DEVICES = [
    {"id": "EDGE-GW-001", "name": "Main Gateway NY", "location": "New York", "type": "Gateway"},
    {"id": "EDGE-GW-002", "name": "Backup Gateway NY", "location": "New York", "type": "Gateway"},
    {"id": "SENSOR-001", "name": "Vibration Sensor A", "location": "Brooklyn Bridge", "type": "Environmental Sensor"},
    {"id": "SENSOR-002", "name": "Temp Sensor B", "location": "Substation 4", "type": "Environmental Sensor"},
    {"id": "NODE-001", "name": "Edge Node Alpha", "location": "Datacenter 1", "type": "Edge Node"},
    {"id": "NODE-002", "name": "Edge Node Beta", "location": "Datacenter 2", "type": "Edge Node"},
    {"id": "NET-SENS-1", "name": "Traffic Analyzer", "location": "Core Switch A", "type": "Network Sensor"},
    {"id": "IOT-CTRL-1", "name": "Pump Controller", "location": "Water Plant 1", "type": "IoT Controller"}
]

class Simulator:
    def __init__(self):
        self.client = mqtt.Client()
        self.running = False
        self.disaster_mode = False
        self.simulation_speed = 5.0
        self.anomaly_type = "none"
        
        # P2P Mesh Topology (Nearest Neighbors)
        self.mesh_topology = {
            "EDGE-GW-001": "SENSOR-001",
            "SENSOR-001": "EDGE-GW-001",
            "EDGE-GW-002": "NODE-001",
            "NODE-001": "EDGE-GW-002",
            "SENSOR-002": "NODE-002",
            "NODE-002": "SENSOR-002",
            "NET-SENS-1": "IOT-CTRL-1",
            "IOT-CTRL-1": "NET-SENS-1"
        }

    def set_disaster_mode(self, active: bool, type: str = "none"):
        self.disaster_mode = active
        self.anomaly_type = type
        print(f"Disaster Mode: {active} [{type}]")

    def run(self):
        self.client.connect(MQTT_BROKER, MQTT_PORT, 60)
        self.running = True
        
        # Register devices
        for d in DEVICES:
            self.client.publish(f"{UNIQUE_ID}/devices/register", json.dumps(d))
            
        print("Simulator started.")
        while self.running:
            try:
                offline_devices = set()
                
                if self.disaster_mode and self.anomaly_type in ["ddos", "packet_drop"]:
                    # Simulate a catastrophic failure where specific nodes go completely offline
                    offline_devices = {"SENSOR-001", "NODE-002", "IOT-CTRL-1"}
                    
                for d in DEVICES:
                    dev_id = d["id"]
                    
                    # If device is dead, it cannot send telemetry
                    if dev_id in offline_devices:
                        continue
                        
                    # P2P Neighbor Watchdog Check
                    neighbor = self.mesh_topology.get(dev_id)
                    if neighbor and neighbor in offline_devices:
                        # Throttle peer alerts to avoid mosquitto IP ban
                        if random.random() < 0.05:
                            alert_payload = {
                                "reporter": dev_id,
                                "offline_neighbor": neighbor,
                                "timestamp": time.time(),
                                "message": f"Peer Watchdog Timeout: {dev_id} lost contact with neighbor {neighbor}."
                            }
                            self.client.publish(f"{UNIQUE_ID}/peer_alert/{neighbor}", json.dumps(alert_payload))
    
                    # Baseline Telemetry
                    latency = 12 + random.uniform(0, 8)
                    packet_loss = random.uniform(0, 0.5)
                    bandwidth = 4.0 + random.uniform(0, 1.5)
                    
                    # Apply anomalies based on disaster state (for surviving devices)
                    if self.disaster_mode:
                        if self.anomaly_type == "latency_spike":
                            latency += random.uniform(150, 400)
                        elif self.anomaly_type == "packet_drop":
                            packet_loss += random.uniform(25, 60)
                            latency += random.uniform(30, 70)
                        elif self.anomaly_type == "ddos":
                            bandwidth += random.uniform(15, 30)
                            latency += random.uniform(100, 300)
                            packet_loss += random.uniform(10, 20)
                        elif self.anomaly_type == "degradation":
                            latency += random.uniform(50, 120)
                            packet_loss += random.uniform(5, 15)
                    
                    payload = {
                        "device_id": dev_id,
                        "latency": latency,
                        "packet_loss": packet_loss,
                        "bandwidth": bandwidth,
                        "timestamp": time.time()
                    }
                    self.client.publish(f"{UNIQUE_ID}/telemetry/{dev_id}", json.dumps(payload))
                    
                time.sleep(1.0 / self.simulation_speed)
            except Exception as e:
                print(f"[SIMULATOR CRASH] {e}")

simulator_engine = Simulator()
