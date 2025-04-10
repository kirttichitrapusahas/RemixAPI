import os
import json
from pyngrok import ngrok
import subprocess
import time

# Set the port your Flask app runs on
PORT = 10000

# Open an ngrok tunnel
public_url = ngrok.connect(PORT)
print(f"🌍 Public URL for Remix API: {public_url}")

# Save the public URL as an environment variable
os.environ["PUBLIC_URL"] = public_url.public_url

# Write it to a JSON file for the Flask app to read
with open("ngrok_url.json", "w") as f:
    json.dump({"url": public_url.public_url}, f)

# Start the Flask server
print("🚀 Starting Flask Remix API server...")
subprocess.Popen(["python", "app.py"])

# Keep this script running so ngrok tunnel stays alive
try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print("\n🛑 Shutting down...")
    ngrok.kill()
