import re

with open('main.py', 'r') as f:
    content = f.read()

# Remove the bad loop creation
content = re.sub(r'''try:
    loop = asyncio\.get_running_loop\(\)
except RuntimeError:
    loop = asyncio\.new_event_loop\(\)
    threading\.Thread\(target=loop\.run_forever, daemon=True\)\.start\(\)''', 'uvicorn_loop = None', content)

# Update startup event
startup_code = '''@app.on_event("startup")
def startup():
    global uvicorn_loop
    uvicorn_loop = asyncio.get_running_loop()
    # Start MQTT Client
    mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
    threading.Thread(target=mqtt_client.loop_forever, daemon=True).start()
    
    # Start Simulator
    threading.Thread(target=simulator_engine.run, daemon=True).start()'''

content = re.sub(r'''@app\.on_event\("startup"\)
def startup\(\):
    # Start MQTT Client
    mqtt_client\.connect\(MQTT_BROKER, MQTT_PORT, 60\)
    threading\.Thread\(target=mqtt_client\.loop_forever, daemon=True\)\.start\(\)
    
    # Start Simulator
    threading\.Thread\(target=simulator_engine\.run, daemon=True\)\.start\(\)''', startup_code, content)

# Replace loop with uvicorn_loop in run_coroutine_threadsafe
content = content.replace(', loop)', ', uvicorn_loop)')

with open('main.py', 'w') as f:
    f.write(content)
print("Loop fixed")
