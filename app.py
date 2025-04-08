from flask import Flask, request, jsonify
import firebase_admin
from firebase_admin import credentials, firestore
import uuid
import logging

# Firebase initialization
if not firebase_admin._apps:
    cred = credentials.Certificate("firebase_credentials.json")
    firebase_admin.initialize_app(cred)

db = firestore.client()

# Logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Flask app setup
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
        db.collection("remix_jobs").document(job_id).set({
            "status": "pending",
            "instrumental_url": instrumental_url,
            "vocals_url": vocals_url,
            "remix_url": "",
            "created_at": firestore.SERVER_TIMESTAMP
        })

        logger.info(f"🎵 Remix job {job_id} created.")
        return jsonify({"job_id": job_id, "status": "pending"}), 200

    except Exception as e:
        logger.exception("Failed to create remix job.")
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
