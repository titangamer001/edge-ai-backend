import time
import json
import random
import threading
import paho.mqtt.client as mqtt

MQTT_BROKER = "broker.emqx.io"
MQTT_PORT = 1883
UNIQUE_ID = "edgeai_sim_102030"

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
        self.simulation_speed = 1.0
        self.anomaly_type = "none"

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
            for d in DEVICES:
                # Baseline
                latency = 12 + random.uniform(0, 8)
                packet_loss = random.uniform(0, 0.5)
                bandwidth = 4.0 + random.uniform(0, 1.5)
                
                # Apply anomalies based on disaster state
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
                        # Gradual failure
                        latency += random.uniform(50, 120)
                        packet_loss += random.uniform(5, 15)
                
                payload = {
                    "device_id": d["id"],
                    "latency": latency,
                    "packet_loss": packet_loss,
                    "bandwidth": bandwidth,
                    "timestamp": time.time()
                }
                self.client.publish(f"{UNIQUE_ID}/telemetry/{d['id']}", json.dumps(payload))
                
            time.sleep(1.0 / self.simulation_speed)

simulator_engine = Simulator()
