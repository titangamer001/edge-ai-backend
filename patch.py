import sys

with open('main.py', 'r') as f:
    content = f.read()

peer_alert_code = '''            # Broadcast alerts if any
            if is_anomaly:
                alert_data = {
                    "device_id": device_id,
                    "severity": severity,
                    "message": msg_text,
                    "timestamp": payload["timestamp"]
                }
                asyncio.run_coroutine_threadsafe(manager.broadcast({"type": "alert", "data": alert_data}), loop)

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
                asyncio.run_coroutine_threadsafe(manager.broadcast({"type": "alert", "data": alert_data}), loop)
                
                # Discord Webhook Notification
                try:
                    from notifier import trigger_external_alert
                    trigger_external_alert(offline_dev, "critical", msg_text)
                except:
                    pass

            # EDGE AI PROXY RECOVERY: Fetch last known good data for the offline device
            from database import Telemetry
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
                asyncio.run_coroutine_threadsafe(manager.broadcast({"type": "telemetry", "data": proxy_payload}), loop)
'''

# Find the spot to inject
if 'elif "/peer_alert/"' not in content:
    content = content.replace('''            # Broadcast alerts if any
            if is_anomaly:
                alert_data = {
                    "device_id": device_id,
                    "severity": severity,
                    "message": msg_text,
                    "timestamp": payload["timestamp"]
                }
                asyncio.run_coroutine_threadsafe(manager.broadcast({"type": "alert", "data": alert_data}), loop)''', peer_alert_code)

    with open('main.py', 'w') as f:
        f.write(content)
        print("Patched main.py")
else:
    print("Already patched")
