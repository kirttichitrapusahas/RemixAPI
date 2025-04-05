from flask import Flask, request, jsonify
import os
import uuid
import subprocess
import requests
import logging

# Firebase Admin
import firebase_admin
from firebase_admin import credentials, storage

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)


# Firebase Init
cred = credentials.Certificate("firebase_credentials.json")
firebase_admin.initialize_app(cred, {
    'storageBucket': 'ai-song-generator-d228c.firebasestorage.app'
})
bucket = storage.bucket()

CURRENT_DIR = os.getcwd()
OUTPUT_DIR = os.path.join(CURRENT_DIR, "outputs")
os.makedirs(OUTPUT_DIR, exist_ok=True)

def download_file(url, filename):
    logger.info(f"📥 Downloading from: {url} -> {filename}")
    r = requests.get(url, stream=True)
    with open(filename, 'wb') as f:
        for chunk in r.iter_content(chunk_size=1024):
            if chunk:
                f.write(chunk)
    logger.info(f"✅ Download complete: {filename}")

@app.route("/")
def home():
    return "🎶 Remix API is running on Render!"

@app.route('/remix', methods=['POST'])
def remix():
    data = request.json
    instrumental_url = data.get("instrumental_url")
    vocals_url = data.get("vocals_url")

    if not instrumental_url or not vocals_url:
        logger.error("❌ Missing URL(s) in request")
        return jsonify({"error": "Both URLs are required"}), 400

    session_id = str(uuid.uuid4())
    instrumental_path = f"{session_id}_instr.mp3"
    vocals_path = f"{session_id}_vocals.mp3"
    remix_filename = f"{session_id}_remix.mp3"
    remix_path = os.path.join(OUTPUT_DIR, remix_filename)

    try:
        logger.info(f"🆔 Session ID: {session_id}")
        download_file(instrumental_url, instrumental_path)
        download_file(vocals_url, vocals_path)

        command = [
            "ffmpeg",
            "-i", instrumental_path,
            "-i", vocals_path,
            "-filter_complex", "[0:a][1:a]amix=inputs=2:duration=first",
            remix_path
        ]
        logger.info(f"▶️ Running FFmpeg: {' '.join(command)}")
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        if result.returncode != 0:
            logger.error(f"❌ FFmpeg failed:\n{result.stderr.decode()}")
            return jsonify({"error": "Remix failed", "details": result.stderr.decode()}), 500

        if not os.path.exists(remix_path):
            return jsonify({"error": "Remix file was not created"}), 500

        # Upload to Firebase Storage
        blob = bucket.blob(f"remixes/{remix_filename}")
        blob.upload_from_filename(remix_path)
        blob.make_public()  # Optional: Make file public

        logger.info(f"✅ Uploaded to Firebase: {blob.public_url}")

        return jsonify({
            "remix_url": blob.public_url
        })

    except Exception as e:
        logger.exception("🔥 Exception during remix process")
        return jsonify({"error": str(e)}), 500
    finally:
        for f in [instrumental_path, vocals_path, remix_path]:
            if os.path.exists(f):
                os.remove(f)

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(debug=True, host="0.0.0.0", port=port)
