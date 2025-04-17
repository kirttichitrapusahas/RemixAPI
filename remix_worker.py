import os
import time
import uuid
import subprocess
import logging
import json
import base64
import shutil
import firebase_admin
from firebase_admin import credentials, firestore
from google.cloud import storage as gcs
from urllib.parse import urlparse, unquote

# ✅ Firebase setup
if not firebase_admin._apps:
    firebase_b64 = os.getenv("FIREBASE_CREDENTIALS_B64")

    if not firebase_b64:
        try:
            with open("firebase_credentials.b64.txt", "r") as f:
                firebase_b64 = f.read().strip()
        except FileNotFoundError:
            raise ValueError("Missing FIREBASE_CREDENTIALS_B64 environment variable or firebase_credentials.b64.txt file")

    cred_dict = json.loads(base64.b64decode(firebase_b64))
    cred = credentials.Certificate(cred_dict)
    firebase_admin.initialize_app(cred, {
        'storageBucket': 'ai-song-generator-d228c.firebasestorage.app'
    })

# Firestore client
db = firestore.client()

# GCS client for reliable downloads
gcs_client = gcs.Client()
bucket = gcs_client.bucket('ai-song-generator-d228c.firebasestorage.app')

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

REMIX_DIR = "outputs_file"
os.makedirs(REMIX_DIR, exist_ok=True)


def download_file(url, filename):
    """
    Download a file from Firebase Storage via the Google Cloud Storage SDK.
    Uses blob.download_to_filename() with built-in retries and resumable support.
    """
    logger.info(f"⬇️ Downloading from {url} to {filename}")

    # Extract blob path from URL
    parsed = urlparse(url)
    # URL-encoded path after '/o/'
    encoded_path = parsed.path.split('/o/')[1]
    blob_name = unquote(encoded_path)

    blob = bucket.blob(blob_name)
    try:
        blob.download_to_filename(filename)
        logger.info(f"✅ Downloaded {filename}")
    except Exception as e:
        logger.error(f"❌ GCS SDK download failed for {blob_name}: {e}")
        raise


def convert_to_wav(input_mp3, output_wav):
    logger.info(f"🎧 Converting {input_mp3} to WAV...")
    subprocess.run(["ffmpeg", "-y", "-i", input_mp3, output_wav], check=True)
    logger.info(f"✅ Converted to {output_wav}")


def trim_audio(input_path, output_path, duration=60):
    logger.info(f"✂️ Trimming {input_path} to {duration} seconds...")
    subprocess.run([
        "ffmpeg", "-y", "-i", input_path,
        "-t", str(duration),
        "-vn",
        "-acodec", "libmp3lame",
        "-ar", "44100",
        "-b:a", "192k",
        output_path
    ], check=True)
    logger.info(f"✅ Trimmed and re-encoded to {output_path}")


def split_audio_with_spleeter(input_path, output_dir):
    abs_input_path = os.path.abspath(input_path)
    abs_output_dir = os.path.abspath(output_dir)

    logger.info(f"📂 Input path: {abs_input_path}")
    logger.info(f"📁 Output dir: {abs_output_dir}")

    try:
        subprocess.run([
            'python', '-m', 'spleeter', 'separate',
            input_path,
            '-p', 'spleeter:2stems',
            '-o', output_dir
        ], check=True)
        logger.info("✅ Spleeter processing completed")
    except subprocess.CalledProcessError as e:
        logger.error(f"❌ Spleeter processing failed: {e}")
        raise


def merge_audio(instr_path, vocal_path, output_path):
    logger.info(f"🎚️ Mixing {instr_path} + {vocal_path} -> {output_path}")
    subprocess.run([
        "ffmpeg", "-y",
        "-i", instr_path,
        "-i", vocal_path,
        "-filter_complex", "[0:a][1:a]amix=inputs=2:duration=first:dropout_transition=3",
        output_path
    ], check=True)
    logger.info(f"✅ Merged to {output_path}")


def upload_to_firebase(filepath):
    filename = os.path.basename(filepath)
    fb_bucket = firebase_admin.storage.bucket()
    blob = fb_bucket.blob(f"remixes/{filename}")
    blob.upload_from_filename(filepath)
    blob.make_public()
    public_url = blob.public_url
    logger.info(f"✅ Uploaded and made public: {public_url}")
    return public_url


def deleteAllRemixes():
    """
    Deletes all files inside the "remixes/" folder in Firebase Storage.
    """
    try:
        blobs = firebase_admin.storage.bucket().list_blobs(prefix="remixes/")
        for blob in blobs:
            blob.delete()
            logger.info(f"🗑️ Deleted file: {blob.name}")
        logger.info("✅ All files in the 'remixes/' folder have been deleted.")
    except Exception as e:
        logger.error(f"❌ Failed to delete files in the 'remixes/' folder: {e}")


def cleanupFiles(file_list, dir_list):
    for file_path in file_list:
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                logger.info(f"🗑️ Deleted file: {file_path}")
        except Exception as e:
            logger.error(f"❌ Could not delete file {file_path}: {e}")
    for dir_path in dir_list:
        try:
            if os.path.exists(dir_path):
                shutil.rmtree(dir_path)
                logger.info(f"🗑️ Deleted directory: {dir_path}")
        except Exception as e:
            logger.error(f"❌ Could not delete directory {dir_path}: {e}")


def process_job(job):
    job_id = job.id
    data = job.to_dict()
    logger.info(f"⚙️ Starting job {job_id}")

    instr_url = data['instrumental_url']
    vocals_url = data['vocals_url']

    instr_mp3 = f"{job_id}_instr.mp3"
    voc_mp3 = f"{job_id}_vocals.mp3"
    instr_trimmed = f"{job_id}_instr_trimmed.mp3"
    voc_trimmed = f"{job_id}_vocals_trimmed.mp3"
    instr_wav = f"{job_id}_instr.wav"
    voc_wav = f"{job_id}_vocals.wav"
    remix_path = f"{job_id}_remix.mp3"

    instr_folder = os.path.splitext(instr_wav)[0]
    voc_folder = os.path.splitext(voc_wav)[0]

    try:
        download_file(instr_url, instr_mp3)
        download_file(vocals_url, voc_mp3)

        trim_audio(instr_mp3, instr_trimmed)
        trim_audio(voc_mp3, voc_trimmed)

        os.remove(instr_mp3)
        os.remove(voc_mp3)

        trimmed_instr_url = upload_to_firebase(instr_trimmed)
        trimmed_vocal_url = upload_to_firebase(voc_trimmed)

        db.collection("remix_jobs").document(job_id).update({
            "trimmed_instr_url": trimmed_instr_url,
            "trimmed_vocal_url": trimmed_vocal_url
        })

        convert_to_wav(instr_trimmed, instr_wav)
        convert_to_wav(voc_trimmed, voc_wav)

        split_audio_with_spleeter(instr_wav, ".")
        split_audio_with_spleeter(voc_wav, ".")

        instr_final = os.path.join(instr_folder, "accompaniment.wav")
        voc_final   = os.path.join(voc_folder, "vocals.wav")

        if not os.path.exists(instr_final):
            raise FileNotFoundError(f"Instrumental not found at {instr_final}")
        if not os.path.exists(voc_final):
            raise FileNotFoundError(f"Vocals not found at {voc_final}")

        merge_audio(instr_final, voc_final, remix_path)
        remix_url = upload_to_firebase(remix_path)

        db.collection("remix_jobs").document(job_id).update({
            "status": "done",
            "remix_url": remix_url
        })
        logger.info(f"✅ Job {job_id} complete - {remix_url}")

    except Exception as e:
        logger.exception(f"❌ Failed job {job_id}: {e}")
        db.collection("remix_jobs").document(job_id).update({
            "status": "error",
            "error": str(e)
        })
    finally:
        file_list = [instr_trimmed, voc_trimmed, instr_wav, voc_wav, remix_path]
        dir_list = [instr_folder, voc_folder]
        cleanupFiles(file_list, dir_list)
        deleteAllRemixes()


def watch_queue():
    logger.info("👀 Watching for pending jobs...")
    while True:
        pending_jobs = db.collection("remix_jobs").where("status", "==", "pending").stream()
        for job in pending_jobs:
            logger.info(f"🎬 Starting job {job.id}")
            db.collection("remix_jobs").document(job.id).update({"status": "processing"})
            process_job(job)
        time.sleep(5)

if __name__ == '__main__':
    logger.info("🚀 Remix Worker Started")
    watch_queue()
