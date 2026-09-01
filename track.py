import re

with open('main.py', 'r') as f:
    content = f.read()

broadcast_code = '''    async def broadcast(self, message: dict):
        #print(f"Broadcasting to {len(self.active_connections)} connections")
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                print(f"Broadcast error: {e}")'''

content = re.sub(r'''    async def broadcast\(self, message: dict\):
        for connection in self\.active_connections:
            try:
                await connection\.send_json\(message\)
            except:
                pass''', broadcast_code, content)

with open('main.py', 'w') as f:
    f.write(content)
print("Added error tracking to broadcast")
