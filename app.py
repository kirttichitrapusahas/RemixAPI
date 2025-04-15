from flask import Flask, request, jsonify
import firebase_admin
from firebase_admin import credentials, firestore
import uuid
import logging
import threading
import os
import base64
import json

from remix_worker import process_job

# Load base64 from file if not set in env
if "FIREBASE_CREDENTIALS_B64" not in os.environ:
    try:
        with open("firebase_credentials.b64.txt", "r") as f:
            os.environ["FIREBASE_CREDENTIALS_B64"] = f.read().strip()
    except FileNotFoundError:
        raise ValueError("Missing FIREBASE_CREDENTIALS_B64 environment variable and firebase_credentials.b64.txt file")

# Initialize Firebase
if not firebase_admin._apps:
    firebase_b64 = os.getenv("FIREBASE_CREDENTIALS_B64")
    if firebase_b64:
        cred_dict = json.loads(base64.b64decode(firebase_b64))
        cred = credentials.Certificate(cred_dict)
        firebase_admin.initialize_app(cred)
    else:
        raise ValueError("Missing FIREBASE_CREDENTIALS_B64 environment variable")

db = firestore.client()

# ✅ Logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ✅ Flask setup
app = Flask(__name__)

@app.route("/")
def home():
    return "Remix API is running!"

@app.route("/remix", methods=["POST"])
def remix():
    try:
        data = request.get_json()
        instrumental_url = data["instrumental_url"]
        vocals_url = data["vocals_url"]

        job_id = str(uuid.uuid4())
        job_ref = db.collection("remix_jobs").document(job_id)
        job_ref.set({
            "status": "pending",
            "instrumental_url": instrumental_url,
            "vocals_url": vocals_url,
            "remix_url": "",
            "created_at": firestore.SERVER_TIMESTAMP
        })

        logger.info(f"🎵 Remix job {job_id} created. Spawning worker thread...")

        def background_remix():
            try:
                logger.info(f"🚀 Thread started for job {job_id}")
                job = job_ref.get()
                process_job(job)
                logger.info(f"✅ Job {job_id} completed")
            except Exception as e:
                logger.exception(f"❌ Failed to process job {job_id}")

        threading.Thread(target=background_remix).start()

        return jsonify({"job_id": job_id, "status": "processing"}), 202

    except Exception as e:
        logger.exception("Failed to create remix job.")
        return jsonify({"error": str(e)}), 500

# ✅ Optional legacy endpoint (if needed)
@app.route("/ngrok-url")
def get_ngrok_url():
    try:
        with open("ngrok_url.json", "r") as f:
            data = json.load(f)
        return jsonify({"url": data.get("url")})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ✅ Save URL to Firestore
def update_remix_api_url_in_firestore(public_url):
    try:
        config_ref = db.collection("remix_config").document("server")
        config_ref.set({"url": public_url}, merge=True)
        logger.info(f"🔥 Public Remix API URL saved to Firestore: {public_url}")
    except Exception as e:
        logger.exception("❌ Failed to save Remix API URL to Firestore.")

# ✅ Startup logic
if __name__ == "__main__":
    print("🚀 Remix API Server is starting...")

    public_url = os.getenv("PUBLIC_URL")  # ← make sure this is passed in env vars
    if not public_url:
        raise ValueError("PUBLIC_URL environment variable is required on RunPod")

    update_remix_api_url_in_firestore(public_url)

    port = int(os.environ.get("PORT", 8080))
    app.run(debug=True, host="0.0.0.0", port=port)
