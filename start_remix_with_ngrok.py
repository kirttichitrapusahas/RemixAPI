import os
from pyngrok import ngrok
import subprocess
import time

# Set the port your Flask app runs on
PORT = 10000

# Open an ngrok tunnel
public_url = ngrok.connect(PORT)
print(f"🌍 Public URL for Remix API: {public_url}")

# Optional: Set this URL as an env variable if needed
os.environ["PUBLIC_URL"] = public_url

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
