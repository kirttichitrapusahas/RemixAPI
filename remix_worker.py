import os, time, uuid, subprocess, requests, logging
import firebase_admin
from firebase_admin import credentials, firestore, storage
from spleeter.separator import Separator

# Firebase setup
if not firebase_admin._apps:
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
    try:
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
    except subprocess.CalledProcessError as e:
        logging.error(f"❌ FFmpeg trimming failed: {e}")
        raise

def split_audio_with_spleeter(input_wav, output_dir):
    try:
        logger.info(f"🎼 Splitting {input_wav} using Spleeter library...")

        if not os.path.exists(input_wav):
            raise FileNotFoundError(f"{input_wav} does not exist")

        file_size = os.path.getsize(input_wav)
        if file_size < 100000:
            raise ValueError(f"⚠️ File size too small: {file_size} bytes — possible invalid audio")

        if os.path.exists(output_dir):
            logger.info(f"🧹 Removing old output dir {output_dir}")
            subprocess.run(["rm", "-rf", output_dir])
        os.makedirs(output_dir, exist_ok=True)

        logger.info(f"📁 File size: {file_size} bytes")
        logger.info(f"📂 Output directory: {output_dir}")

        # 🔄 Use Spleeter's Python API instead of subprocess
        separator = Separator('spleeter:2stems')
        separator.separate_to_file(input_wav, output_dir)

        logger.info(f"✅ Spleeter finished. Output at: {output_dir}")

    except Exception as e:
        logger.exception(f"❌ Error during Spleeter processing: {e}")
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
    bucket = storage.bucket()
    filename = os.path.basename(filepath)
    blob = bucket.blob(f"remixes/{filename}")
    blob.upload_from_filename(filepath)

    # ✅ Make the uploaded file public
    blob.make_public()

    public_url = blob.public_url
    logging.info(f"✅ Uploaded and made public: {public_url}")
    return public_url

def process_job(job):
    job_id = job.id
    data = job.to_dict()
    logger.info(f"⚙️ Starting job {job_id}")

    instr_url = data['instrumental_url']
    vocals_url = data['vocals_url']
    logger.info(f"🎵 Instrumental URL: {instr_url}")
    logger.info(f"🎤 Vocals URL: {vocals_url}")

    instr_mp3 = f"{job_id}_instr.mp3"
    voc_mp3 = f"{job_id}_vocals.mp3"
    instr_trimmed = f"{job_id}_instr_trimmed.mp3"
    voc_trimmed = f"{job_id}_vocals_trimmed.mp3"
    instr_wav = f"{job_id}_instr.wav"
    voc_wav = f"{job_id}_vocals.wav"

    instr_out_dir = os.path.join(OUTPUT_DIR, f"instr_{job_id}")
    voc_out_dir = os.path.join(OUTPUT_DIR, f"vocals_{job_id}")
    remix_path = os.path.join(OUTPUT_DIR, f"{job_id}_remix.mp3")

    try:
        logger.info("⬇️ Downloading instrumental MP3...")
        download_file(instr_url, instr_mp3)
        logger.info("✅ Downloaded instrumental MP3")

        logger.info("⬇️ Downloading vocal MP3...")
        download_file(vocals_url, voc_mp3)
        logger.info("✅ Downloaded vocal MP3")

        logger.info("✂️ Trimming instrumental...")
        trim_audio(instr_mp3, instr_trimmed)
        logger.info(f"✅ Trimmed instrumental saved to {instr_trimmed}")

        logger.info("✂️ Trimming vocals...")
        trim_audio(voc_mp3, voc_trimmed)
        logger.info(f"✅ Trimmed vocals saved to {voc_trimmed}")

        if os.path.exists(instr_mp3):
            os.remove(instr_mp3)
            logger.info("🗑️ Deleted original instrumental MP3")
        if os.path.exists(voc_mp3):
            os.remove(voc_mp3)
            logger.info("🗑️ Deleted original vocal MP3")

        logger.info("🚀 Uploading trimmed instrumental to Firebase...")
        trimmed_instr_url = upload_to_firebase(instr_trimmed)
        logger.info(f"✅ Uploaded and public URL: {trimmed_instr_url}")

        logger.info("🚀 Uploading trimmed vocals to Firebase...")
        trimmed_vocal_url = upload_to_firebase(voc_trimmed)
        logger.info(f"✅ Uploaded and public URL: {trimmed_vocal_url}")

        logger.info("📝 Updating Firestore with trimmed URLs...")
        db.collection("remix_jobs").document(job_id).update({
            "trimmed_instr_url": trimmed_instr_url,
            "trimmed_vocal_url": trimmed_vocal_url
        })

        logger.info("🎼 Converting trimmed instrumental to WAV...")
        convert_to_wav(instr_trimmed, instr_wav)
        logger.info(f"✅ Converted to WAV: {instr_wav}")

        logger.info("🎼 Converting trimmed vocals to WAV...")
        convert_to_wav(voc_trimmed, voc_wav)
        logger.info(f"✅ Converted to WAV: {voc_wav}")

        logger.info("🔬 Running Spleeter on instrumental...")
        split_audio_with_spleeter(instr_wav, instr_out_dir)
        logger.info("✅ Spleeter finished for instrumental")

        logger.info("🔬 Running Spleeter on vocals...")
        split_audio_with_spleeter(voc_wav, voc_out_dir)
        logger.info("✅ Spleeter finished for vocals")

        instr_final = os.path.join(instr_out_dir, os.path.splitext(instr_wav)[0], "accompaniment.wav")
        voc_final = os.path.join(voc_out_dir, os.path.splitext(voc_wav)[0], "vocals.wav")
        logger.info(f"🎛️ Merging: {instr_final} + {voc_final} -> {remix_path}")

        merge_audio(instr_final, voc_final, remix_path)
        logger.info("✅ Merging complete")

        logger.info("🚀 Uploading remix to Firebase...")
        remix_url = upload_to_firebase(remix_path)
        logger.info(f"✅ Remix uploaded: {remix_url}")

        logger.info("📝 Updating Firestore with remix URL and status...")
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

    finally:
        logger.info(f"🧹 Cleaning up files for job {job_id}")
        for f in [instr_trimmed, voc_trimmed, instr_wav, voc_wav, remix_path]:
            if os.path.exists(f):
                os.remove(f)
                logger.info(f"🗑️ Deleted {f}")
        for d in [instr_out_dir, voc_out_dir]:
            if os.path.exists(d):
                subprocess.run(["rm", "-rf", d])
                logger.info(f"🗑️ Deleted directory {d}")

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
