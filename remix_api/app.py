from flask import Flask, request, jsonify
import os
import uuid
import subprocess
import requests
import logging
import firebase_admin
from firebase_admin import credentials, storage
from spleeter.separator import Separator

# Setup Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Firebase Init
cred = credentials.Certificate("firebase_credentials.json")
firebase_admin.initialize_app(cred, {
    'storageBucket': 'ai-song-generator-d228c.firebasestorage.app'
})
bucket = storage.bucket()

# Directory Setup
CURRENT_DIR = os.getcwd()
OUTPUT_DIR = os.path.join(CURRENT_DIR, "outputs")
os.makedirs(OUTPUT_DIR, exist_ok=True)

def download_file(url, filename):
    logger.info(f"📥 Downloading from: {url}")
    r = requests.get(url, stream=True)
    with open(filename, 'wb') as f:
        for chunk in r.iter_content(1024):
            if chunk:
                f.write(chunk)
    logger.info(f"✅ Download complete: {filename}")

def convert_to_wav(input_mp3, output_wav):
    logger.info(f"🔄 Converting to WAV: {input_mp3} → {output_wav}")
    command = ["ffmpeg", "-y", "-i", input_mp3, output_wav]
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        logger.error(f"❌ FFmpeg failed:\n{result.stderr}")
        raise Exception(f"FFmpeg conversion failed: {result.stderr}")
    logger.info(f"✅ Conversion complete: {output_wav}")

def split_audio_with_spleeter(input_wav, output_dir, session_id):
    try:
        logger.info(f"🎼 [{session_id}] Starting Spleeter separation: {input_wav}")
        separator = Separator('spleeter:2stems', multiprocess=False)  # Reduced memory
        separator.separate_to_file(input_wav, output_dir)
        logger.info(f"✅ [{session_id}] Spleeter separation complete: {output_dir}")
    except Exception as e:
        logger.error(f"❌ [{session_id}] Spleeter failed: {str(e)}")
        raise

def merge_audio(instrumental_path, vocal_path, output_path, session_id):
    logger.info(f"🎛️ [{session_id}] Merging audio using FFmpeg")
    command = [
        "ffmpeg", "-y",
        "-i", instrumental_path,
        "-i", vocal_path,
        "-filter_complex", "[0:a][1:a]amix=inputs=2:duration=first:dropout_transition=3",
        output_path
    ]
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        logger.error(f"❌ [{session_id}] FFmpeg merge failed:\n{result.stderr}")
        raise Exception(f"FFmpeg merge failed: {result.stderr}")
    logger.info(f"✅ [{session_id}] Merge complete: {output_path}")

@app.route("/")
def home():
    return "🎶 Remix API is running!"

@app.route('/remix', methods=['POST'])
def remix():
    data = request.json
    instrumental_url = data.get("instrumental_url")
    vocals_url = data.get("vocals_url")

    if not instrumental_url or not vocals_url:
        return jsonify({"error": "Both instrumental_url and vocals_url are required"}), 400

    session_id = str(uuid.uuid4())[:8]
    logger.info(f"🆕 [{session_id}] New remix session started")

    instr_mp3 = f"{session_id}_instr.mp3"
    voc_mp3 = f"{session_id}_vocals.mp3"
    instr_wav = f"{session_id}_instr.wav"
    voc_wav = f"{session_id}_vocals.wav"

    instr_out_dir = os.path.join(OUTPUT_DIR, f"instr_{session_id}")
    voc_out_dir = os.path.join(OUTPUT_DIR, f"vocals_{session_id}")
    remix_path = os.path.join(OUTPUT_DIR, f"{session_id}_remix.mp3")

    try:
        logger.info(f"⬇️ [{session_id}] Downloading audio files...")
        download_file(instrumental_url, instr_mp3)
        download_file(vocals_url, voc_mp3)

        logger.info(f"🎧 [{session_id}] Converting MP3s to WAV...")
        convert_to_wav(instr_mp3, instr_wav)
        convert_to_wav(voc_mp3, voc_wav)

        logger.info(f"🔍 [{session_id}] Starting Spleeter separation")
        split_audio_with_spleeter(instr_wav, instr_out_dir, session_id)
        split_audio_with_spleeter(voc_wav, voc_out_dir, session_id)

        instr_base = os.path.splitext(os.path.basename(instr_wav))[0]
        voc_base = os.path.splitext(os.path.basename(voc_wav))[0]

        instrumental_out = os.path.join(instr_out_dir, instr_base, "accompaniment.wav")
        vocals_out = os.path.join(voc_out_dir, voc_base, "vocals.wav")

        if not os.path.exists(instrumental_out) or not os.path.exists(vocals_out):
            raise Exception(f"❌ [{session_id}] Spleeter output files missing!")

        logger.info(f"🔀 [{session_id}] Merging instrumental and vocals")
        merge_audio(instrumental_out, vocals_out, remix_path, session_id)

        logger.info(f"☁️ [{session_id}] Uploading remix to Firebase...")
        blob = bucket.blob(f"remixes/{os.path.basename(remix_path)}")
        blob.upload_from_filename(remix_path)
        blob.make_public()
        logger.info(f"🚀 [{session_id}] Remix uploaded successfully: {blob.public_url}")

        return jsonify({"remix_url": blob.public_url})

    except Exception as e:
        logger.exception(f"🔥 [{session_id}] Remix generation failed")
        return jsonify({"error": str(e)}), 500

    finally:
        logger.info(f"🧹 [{session_id}] Cleaning up temp files...")
        for f in [instr_mp3, voc_mp3, instr_wav, voc_wav, remix_path]:
            if os.path.exists(f):
                os.remove(f)
        for d in [instr_out_dir, voc_out_dir]:
            if os.path.exists(d):
                subprocess.run(["rm", "-rf", d])
        logger.info(f"✅ [{session_id}] Cleanup complete.")

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    logger.info(f"🚀 Starting Remix API server on port {port}")
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
