from flask import Flask, request, jsonify
import firebase_admin
from firebase_admin import credentials, firestore
import uuid
import logging
import threading

from remix_worker import process_job

# Firebase setup
if not firebase_admin._apps:
    cred = credentials.Certificate("firebase_credentials.json")
    firebase_admin.initialize_app(cred)

db = firestore.client()

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Flask setup
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

        # ✅ Background thread to avoid timeout
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

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=8080)
