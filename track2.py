import re

with open('main.py', 'r') as f:
    content = f.read()

content = content.replace('def on_message(client, userdata, msg):', 'def on_message(client, userdata, msg):\n    print(f"MQTT Recv: {msg.topic}")')

with open('main.py', 'w') as f:
    f.write(content)
print("Added on_message logging")
