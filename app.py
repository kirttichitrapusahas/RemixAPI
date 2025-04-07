import logging
import sys
from flask import Flask, request, jsonify
import uuid
import os
import subprocess  # For running remix_worker.py
import firebase_admin
from firebase_admin import credentials, firestore

# Setup logger to send logs to stdout
logging.basicConfig(stream=sys.stdout, level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Firebase initialization
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
        logger.error("Missing URLs for remix job")
        return jsonify({"error": "Missing URLs"}), 400

    job_id = str(uuid.uuid4())[:8]
    job_data = {
        "job_id": job_id,
        "instrumental_url": instrumental_url,
        "vocals_url": vocals_url,
        "status": "pending",
        "remix_url": ""
    }

    # Save job data in Firestore
    db.collection("remix_jobs").document(job_id).set(job_data)
    logger.info(f"Remix job submitted with job_id: {job_id}")

    # Trigger remix_worker.py after job is created
    try:
        # Call remix_worker.py to process the job asynchronously
        subprocess.Popen(['python', 'remix_worker.py', job_id, instrumental_url, vocals_url])
        logger.info(f"Remix worker triggered for job_id: {job_id}")
    except Exception as e:
        logger.error(f"Failed to trigger remix worker for job_id {job_id}: {str(e)}")

    return jsonify({"message": "Remix job submitted", "job_id": job_id}), 200

# New route for checking job status by job_id
@app.route('/remix/<job_id>', methods=['GET'])
def get_remix_status(job_id):
    # Fetch the job from Firestore using the job_id
    job_ref = db.collection("remix_jobs").document(job_id)
    job = job_ref.get()

    if job.exists:
        job_data = job.to_dict()
        logger.info(f"Job status for {job_id}: {job_data['status']}")
        return jsonify(job_data), 200
    else:
        logger.error(f"Job not found for job_id: {job_id}")
        return jsonify({"error": "Job not found"}), 404

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    logger.info(f"🚀 Starting Remix API server on port {port}")
    app.run(host="0.0.0.0", port=port, debug=True, use_reloader=False)
