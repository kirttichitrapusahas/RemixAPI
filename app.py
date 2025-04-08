import sys
import os
import logging
import uuid
import requests
import subprocess
import firebase_admin
from firebase_admin import credentials, firestore
from upload_to_firebase import uploadAudioToFirebase  # Assuming this is your upload method

# Setup logging
logging.basicConfig(stream=sys.stdout, level=logging.INFO)
logger = logging.getLogger(__name__)

# Firebase initialization (only if not already initialized)
if not firebase_admin._apps:
    cred = credentials.Certificate("firebase_credentials.json")
    firebase_admin.initialize_app(cred)

db = firestore.client()

def download_audio(url, filename):
    r = requests.get(url)
    with open(filename, 'wb') as f:
        f.write(r.content)
    logger.info(f"Downloaded: {filename}")

def trim_audio(input_path, output_path, duration=60):
    command = [
        "ffmpeg",
        "-y",
        "-i", input_path,
        "-t", str(duration),
        "-c", "copy",
        output_path
    ]
    subprocess.run(command, check=True)
    logger.info(f"Trimmed audio: {output_path}")

def remix_audio(instrumental_file, vocals_file, output_file):
    command = [
        "ffmpeg",
        "-y",
        "-i", instrumental_file,
        "-i", vocals_file,
        "-filter_complex", "[0:a][1:a]amix=inputs=2:duration=shortest",
        output_file
    ]
    subprocess.run(command, check=True)
    logger.info(f"Remixed audio saved: {output_file}")

def process_job(job_id, instrumental_url, vocals_url):
    logger.info(f"🔧 Processing job {job_id}...")

    instrumental_raw = f"{job_id}_instrumental.mp3"
    vocals_raw = f"{job_id}_vocals.mp3"
    instrumental_trimmed = f"{job_id}_instrumental_trimmed.mp3"
    vocals_trimmed = f"{job_id}_vocals_trimmed.mp3"
    output_file = f"{job_id}_remix.mp3"

    try:
        download_audio(instrumental_url, instrumental_raw)
        download_audio(vocals_url, vocals_raw)

        trim_audio(instrumental_raw, instrumental_trimmed)
        trim_audio(vocals_raw, vocals_trimmed)

        # Cleanup raw files
        os.remove(instrumental_raw)
        os.remove(vocals_raw)

        remix_audio(instrumental_trimmed, vocals_trimmed, output_file)

        # Upload to Firebase
        remix_url = uploadAudioToFirebase(output_file)

        # Update Firestore
        db.collection("remix_jobs").document(job_id).update({
            "status": "completed",
            "remix_url": remix_url
        })
        logger.info(f"✅ Remix job {job_id} completed! URL: {remix_url}")

    except Exception as e:
        logger.error(f"❌ Remix job {job_id} failed: {str(e)}")
        db.collection("remix_jobs").document(job_id).update({
            "status": "failed",
            "remix_url": ""
        })

    finally:
        # Clean up all files
        for f in [instrumental_trimmed, vocals_trimmed, output_file]:
            if os.path.exists(f):
                os.remove(f)

if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Usage: python remix_worker.py <job_id> <instrumental_url> <vocals_url>")
        sys.exit(1)

    job_id = sys.argv[1]
    instrumental_url = sys.argv[2]
    vocals_url = sys.argv[3]

    process_job(job_id, instrumental_url, vocals_url)
