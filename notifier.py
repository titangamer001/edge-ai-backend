import subprocess
import urllib.request
import json
import time

# Cooldown to prevent spamming notifications (seconds)
ALERT_COOLDOWN = 15
_last_alert_time = 0

# Set your Slack/Discord Webhook URL here to receive real messages over the internet
WEBHOOK_URL = "https://discord.com/api/webhooks/1544273629301448725/2Vs-8c5F9GHZQDw3kRy__Mumtlth-SzavevEAIX5WNqrF2WHmFtcQL1426EVFSnnDkAt"

def trigger_external_alert(device_id, severity, message):
    global _last_alert_time
    now = time.time()
    
    # Global cooldown to avoid Discord 429 Rate Limit
    if severity != "stable":
        if now - _last_alert_time < ALERT_COOLDOWN:
            return
        _last_alert_time = now
    
    # 1. Windows Native Toast Notification
    title = f"EDGE AI [{severity.upper()}] - {device_id}"
    
    ps_script = f"""
    [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
    [Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null
    $template = @"
    <toast>
        <visual>
            <binding template="ToastText02">
                <text id="1">{title}</text>
                <text id="2">{message}</text>
            </binding>
        </visual>
        <audio src="ms-winsoundevent:Notification.Looping.Alarm" loop="false"/>
    </toast>
    "@
    $xml = New-Object Windows.Data.Xml.Dom.XmlDocument
    $xml.LoadXml($template)
    $toast = New-Object Windows.UI.Notifications.ToastNotification $xml
    [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("Edge AI NOC").Show($toast)
    """
    
    try:
        subprocess.run(["powershell", "-WindowStyle", "Hidden", "-Command", ps_script], 
                       creationflags=subprocess.CREATE_NO_WINDOW, timeout=2)
    except Exception as e:
        print(f"[NOTIFIER] Toast failed: {e}")

    # 2. Webhook Notification (Discord / Slack)
    import os
    # Render automatically sets RENDER=true in its environment. 
    # We only fire webhooks if we are on the cloud to prevent duplicate messages from localhost.
    if WEBHOOK_URL and os.environ.get("RENDER") == "true":
        try:
            if severity == "stable":
                embed_color = 65280 # Green
                content_msg = "✅ <@&1430466556869083190> <@1430466556869083190> **SYSTEM RESTORED & STABLE**"
                diff_block = f"```yaml\n+ {message}\n+ AI Engine confirms all network traffic has returned to normal baselines.```"
            else:
                embed_color = 16711680 # Red
                content_msg = "🚨 <@&1430466556869083190> <@1430466556869083190> - **CRITICAL NETWORK INCIDENT DETECTED**"
                diff_block = f"```diff\n- {message}\n- Immediate intervention recommended. Traffic patterns align with known anomaly signatures (e.g. DDoS or Physical Degradation).```"

            payload = {
                "content": content_msg,
                "allowed_mentions": {
                    "parse": ["users", "roles", "everyone"]
                },
                "embeds": [
                    {
                        "title": f"Infrastructure Update: {device_id}",
                        "description": "Edge AI Deep Learning Autoencoder Telemetry Report.",
                        "color": embed_color,
                        "fields": [
                            {
                                "name": "Target Device",
                                "value": f"`{device_id}`",
                                "inline": True
                            },
                            {
                                "name": "Current Status",
                                "value": f"`{severity.upper()}`",
                                "inline": True
                            },
                            {
                                "name": "Diagnostic Details",
                                "value": diff_block,
                                "inline": False
                            }
                        ],
                        "footer": {
                            "text": "Edge AI NOC • PyTorch Autoencoder Inference"
                        }
                    }
                ]
            }
            req = urllib.request.Request(WEBHOOK_URL, method="POST")
            req.add_header('Content-Type', 'application/json')
            req.add_header('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)')
            
            with urllib.request.urlopen(req, data=json.dumps(payload).encode('utf-8')) as response:
                print(f"[NOTIFIER] Sent Webhook for {device_id} (Status: {response.status})")
        except Exception as e:
            print(f"[NOTIFIER] Webhook Failed: {e}")
