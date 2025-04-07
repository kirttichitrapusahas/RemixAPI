from flask import Flask, request, jsonify
import uuid
import os
import firebase_admin
from firebase_admin import credentials, firestore

app = Flask(__name__)

cred = credentials.Certificate("firebase_credentials.json")
firebase_admin.initialize_app(cred)
db = firestore.client()

@app.route('/')
def home():
    return "🎶 Remix API - Job Queue Mode"

@app.route('/remix', methods=['POST'])
def remix_request():
    data = request.json
    instrumental_url = data.get("instrumental_url")
    vocals_url = data.get("vocals_url")

    if not instrumental_url or not vocals_url:
        return jsonify({"error": "Missing URLs"}), 400

    job_id = str(uuid.uuid4())[:8]
    job_data = {
        "job_id": job_id,
        "instrumental_url": instrumental_url,
        "vocals_url": vocals_url,
        "status": "pending",
        "remix_url": ""
    }

    db.collection("remix_jobs").document(job_id).set(job_data)
    return jsonify({"message": "Remix job submitted", "job_id": job_id}), 200

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    logger.info(f"🚀 Starting Remix API server on port {port}")
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
