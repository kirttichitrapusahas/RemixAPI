import os, time, uuid, subprocess, requests, logging
import json
import base64
import firebase_admin
from firebase_admin import credentials, firestore, storage

# ✅ Firebase setup
if not firebase_admin._apps:
    firebase_b64 = os.getenv("FIREBASE_CREDENTIALS_B64")

    if not firebase_b64:
        try:
            with open("firebase_credentials.b64.txt", "r") as f:
                firebase_b64 = f.read().strip()
        except FileNotFoundError:
            raise ValueError("Missing FIREBASE_CREDENTIALS_B64 environment variable or firebase_credentials.b64.txt file")

    # Decode Base64 and parse JSON
    cred_dict = json.loads(base64.b64decode(firebase_b64))
    cred = credentials.Certificate(cred_dict)
    firebase_admin.initialize_app(cred, {
        'storageBucket': 'ai-song-generator-d228c.firebasestorage.app'  # ✅ Correct domain
    })

db = firestore.client()
bucket = storage.bucket()

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

OUTPUT_DIR = "outputs"
os.makedirs(OUTPUT_DIR, exist_ok=True)

def download_file(url, filename):
    logger.info(f"⬇️ Downloading from {url} to {filename}")
    r = requests.get(url, stream=True)
    with open(filename, 'wb') as f:
        for chunk in r.iter_content(1024):
            f.write(chunk)
    logger.info(f"✅ Downloaded {filename}")

def convert_to_wav(input_mp3, output_wav):
    logger.info(f"🎧 Converting {input_mp3} to WAV...")
    subprocess.run(["ffmpeg", "-y", "-i", input_mp3, output_wav], check=True)
    logger.info(f"✅ Converted to {output_wav}")

def trim_audio(input_path, output_path, duration=60):
    logging.info(f"✂️ Trimming {input_path} to {duration} seconds...")
    subprocess.run([
        "ffmpeg", "-y", "-i", input_path,
        "-t", str(duration),
        "-vn",
        "-acodec", "libmp3lame",
        "-ar", "44100",
        "-b:a", "192k",
        output_path
    ], check=True)
    logging.info(f"✅ Trimmed and re-encoded to {output_path}")

def split_audio_with_spleeter(input_path, output_dir):
    abs_input_path = os.path.abspath(input_path)
    abs_output_dir = os.path.abspath(output_dir)

    logging.info(f"📂 Input path: {abs_input_path}")
    logging.info(f"📁 Output dir: {abs_output_dir}")

    try:
        subprocess.run([
            'spleeter', 'separate', '--',
            input_path,
            '-p', 'spleeter:2stems',
            '-o', output_dir
        ], check=True)
        logging.info("✅ Spleeter processing completed")
    except subprocess.CalledProcessError as e:
        logging.error(f"❌ Spleeter processing failed: {e}")
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
    blob = bucket.blob(f"remixes/{filename}")
    blob.upload_from_filename(filepath)
    blob.make_public()
    public_url = blob.public_url
    logger.info(f"✅ Uploaded and made public: {public_url}")
    return public_url

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

    remix_path = os.path.join(OUTPUT_DIR, f"{job_id}_remix.mp3")

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

        instr_out_dir = os.path.join(OUTPUT_DIR, f"instr_{job_id}")
        voc_out_dir = os.path.join(OUTPUT_DIR, f"vocals_{job_id}")

        logger.info("🎧 Splitting files with Spleeter...")
        logger.info(f"🎵 Instrumental WAV: {instr_wav}")
        logger.info(f"🎤 Vocal WAV: {voc_wav}")

        split_audio_with_spleeter(instr_wav, instr_out_dir)
        split_audio_with_spleeter(voc_wav, voc_out_dir)

        instr_name = os.path.splitext(os.path.basename(instr_wav))[0]
        voc_name = os.path.splitext(os.path.basename(voc_wav))[0]

        instr_final = os.path.join(instr_out_dir, instr_name, "accompaniment.wav")
        voc_final = os.path.join(voc_out_dir, voc_name, "vocals.wav")

        logger.info(f"🔍 Instrumental path: {instr_final}")
        logger.info(f"🔍 Vocal path:       {voc_final}")

        if not os.path.exists(instr_final):
            raise FileNotFoundError(f"❌ Instrumental not found at {instr_final}")
        if not os.path.exists(voc_final):
            raise FileNotFoundError(f"❌ Vocals not found at {voc_final}")

        logger.info("✅ Both instrumental and vocal files found. Proceeding to merge.")

        merge_audio(instr_final, voc_final, remix_path)

        remix_url = upload_to_firebase(remix_path)

        db.collection("remix_jobs").document(job_id).update({
            "status": "done",
            "remix_url": remix_url
        })

        logger.info(f"✅ Job {job_id} complete - {remix_url}")

    except Exception as e:
        logger.exception(f"❌ Failed job {job_id}: {str(e)}")
        db.collection("remix_jobs").document(job_id).update({
            "status": "error",
            "error": str(e)
        })

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
