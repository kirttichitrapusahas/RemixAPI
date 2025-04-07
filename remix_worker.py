import os, time, uuid, subprocess, requests, logging
import firebase_admin
from firebase_admin import credentials, firestore, storage
from spleeter.separator import Separator

# Firebase setup
cred = credentials.Certificate("firebase_credentials.json")
firebase_admin.initialize_app(cred, {
    'storageBucket': 'ai-song-generator-d228c.firebasestorage.app'
})
db = firestore.client()
bucket = storage.bucket()

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

OUTPUT_DIR = "outputs"
os.makedirs(OUTPUT_DIR, exist_ok=True)

def download_file(url, filename):
    r = requests.get(url, stream=True)
    with open(filename, 'wb') as f:
        for chunk in r.iter_content(1024):
            f.write(chunk)

def convert_to_wav(input_mp3, output_wav):
    subprocess.run(["ffmpeg", "-y", "-i", input_mp3, output_wav], check=True)

def split_audio_with_spleeter(input_wav, output_dir):
    separator = Separator('spleeter:2stems', multiprocess=False)
    separator.separate_to_file(input_wav, output_dir)

def merge_audio(instr_path, vocal_path, output_path):
    subprocess.run([
        "ffmpeg", "-y",
        "-i", instr_path,
        "-i", vocal_path,
        "-filter_complex", "[0:a][1:a]amix=inputs=2:duration=first:dropout_transition=3",
        output_path
    ], check=True)

def upload_to_firebase(filepath):
    blob = bucket.blob(f"remixes/{os.path.basename(filepath)}")
    blob.upload_from_filename(filepath)
    blob.make_public()
    return blob.public_url

def process_job(job):
    job_id = job.id
    data = job.to_dict()
    logger.info(f"🛠️ Processing job {job_id}")

    instr_url = data['instrumental_url']
    vocals_url = data['vocals_url']

    instr_mp3 = f"{job_id}_instr.mp3"
    voc_mp3 = f"{job_id}_vocals.mp3"
    instr_wav = f"{job_id}_instr.wav"
    voc_wav = f"{job_id}_vocals.wav"

    instr_out_dir = os.path.join(OUTPUT_DIR, f"instr_{job_id}")
    voc_out_dir = os.path.join(OUTPUT_DIR, f"vocals_{job_id}")
    remix_path = os.path.join(OUTPUT_DIR, f"{job_id}_remix.mp3")

    try:
        download_file(instr_url, instr_mp3)
        download_file(vocals_url, voc_mp3)
        convert_to_wav(instr_mp3, instr_wav)
        convert_to_wav(voc_mp3, voc_wav)

        split_audio_with_spleeter(instr_wav, instr_out_dir)
        split_audio_with_spleeter(voc_wav, voc_out_dir)

        instr_final = os.path.join(instr_out_dir, os.path.splitext(instr_wav)[0], "accompaniment.wav")
        voc_final = os.path.join(voc_out_dir, os.path.splitext(voc_wav)[0], "vocals.wav")

        merge_audio(instr_final, voc_final, remix_path)
        remix_url = upload_to_firebase(remix_path)

        db.collection("remix_jobs").document(job_id).update({
            "status": "done",
            "remix_url": remix_url
        })
        logger.info(f"✅ Job {job_id} completed: {remix_url}")

    except Exception as e:
        logger.exception(f"❌ Failed job {job_id}")
        db.collection("remix_jobs").document(job_id).update({
            "status": "error",
            "error": str(e)
        })
    finally:
        for f in [instr_mp3, voc_mp3, instr_wav, voc_wav, remix_path]:
            if os.path.exists(f): os.remove(f)
        for d in [instr_out_dir, voc_out_dir]:
            if os.path.exists(d): subprocess.run(["rm", "-rf", d])

def watch_queue():
    while True:
        pending_jobs = db.collection("remix_jobs").where("status", "==", "pending").stream()
        for job in pending_jobs:
            db.collection("remix_jobs").document(job.id).update({"status": "processing"})
            process_job(job)
        time.sleep(5)

if __name__ == '__main__':
    logger.info("🚀 Remix worker started...")
    watch_queue()
