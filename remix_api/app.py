from flask import Flask, request, jsonify
import os
import uuid
import subprocess
import requests
import logging

# Firebase Admin
import firebase_admin
from firebase_admin import credentials, storage

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Firebase Init
cred = credentials.Certificate("firebase_credentials.json")
firebase_admin.initialize_app(cred, {
    'storageBucket': 'ai-song-generator-d228c.firebasestorage.app'
})
bucket = storage.bucket()

CURRENT_DIR = os.getcwd()
OUTPUT_DIR = os.path.join(CURRENT_DIR, "outputs")
os.makedirs(OUTPUT_DIR, exist_ok=True)

def download_file(url, filename):
    logger.info(f"📥 Downloading from: {url} -> {filename}")
    r = requests.get(url, stream=True)
    with open(filename, 'wb') as f:
        for chunk in r.iter_content(chunk_size=1024):
            if chunk:
                f.write(chunk)
    logger.info(f"✅ Download complete: {filename}")

def split_audio_with_spleeter(input_path, output_dir, stems="2stems"):
    if not os.path.exists(input_path):
        raise Exception(f"Input file not found: {input_path}")

    command = [
        "spleeter", "separate",
        "-p", f"spleeter:{stems}",
        "-o", output_dir,
        input_path
    ]
    logger.info(f"🎼 Running Spleeter: {' '.join(command)}")

    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    if result.returncode != 0:
        logger.error("❌ Spleeter failed with stderr:")
        logger.error(result.stderr)
        raise Exception("Spleeter separation failed")

    logger.info("✅ Spleeter separation complete")

def merge_audio(instrumental_path, vocal_path, output_path):
    if not os.path.exists(instrumental_path):
        raise Exception(f"Instrumental file not found: {instrumental_path}")
    if not os.path.exists(vocal_path):
        raise Exception(f"Vocal file not found: {vocal_path}")

    command = [
        "ffmpeg",
        "-y",  # Overwrite if file exists
        "-i", instrumental_path,
        "-i", vocal_path,
        "-filter_complex", "[0:a][1:a]amix=inputs=2:duration=first:dropout_transition=3",
        output_path
    ]
    logger.info(f"🎛️ Running FFmpeg: {' '.join(command)}")

    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    if result.returncode != 0:
        logger.error("❌ FFmpeg failed with stderr:")
        logger.error(result.stderr)
        raise Exception("FFmpeg merge failed")

    logger.info("✅ FFmpeg merge complete")

@app.route("/")
def home():
    return "🎶 Remix API is running on Render!"

@app.route('/remix', methods=['POST'])
def remix():
    data = request.json
    instrumental_url = data.get("instrumental_url")
    vocals_url = data.get("vocals_url")

    if not instrumental_url or not vocals_url:
        logger.error("❌ Missing URL(s) in request")
        return jsonify({"error": "Both URLs are required"}), 400

    session_id = str(uuid.uuid4())
    instrumental_input = f"{session_id}_instr.mp3"
    vocals_input = f"{session_id}_vocals.mp3"
    instrumental_dir = os.path.join(OUTPUT_DIR, f"instr_{session_id}")
    vocals_dir = os.path.join(OUTPUT_DIR, f"vocals_{session_id}")
    remix_filename = f"{session_id}_remix.mp3"
    remix_path = os.path.join(OUTPUT_DIR, remix_filename)

    try:
        logger.info(f"🆔 Session ID: {session_id}")

        download_file(instrumental_url, instrumental_input)
        download_file(vocals_url, vocals_input)

        split_audio_with_spleeter(instrumental_input, instrumental_dir)
        split_audio_with_spleeter(vocals_input, vocals_dir)

        instr_folder = os.path.splitext(instrumental_input)[0]
        vocal_folder = os.path.splitext(vocals_input)[0]

        instrumental_out = os.path.join(instrumental_dir, instr_folder, "accompaniment.wav")
        vocals_out = os.path.join(vocals_dir, vocal_folder, "vocals.wav")

        logger.info(f"🔍 Checking outputs: {instrumental_out} & {vocals_out}")
        if not os.path.exists(instrumental_out) or not os.path.exists(vocals_out):
            raise Exception("Spleeter output not found")

        merge_audio(instrumental_out, vocals_out, remix_path)

        blob = bucket.blob(f"remixes/{remix_filename}")
        blob.upload_from_filename(remix_path)
        blob.make_public()

        logger.info(f"✅ Uploaded to Firebase: {blob.public_url}")

        return jsonify({
            "remix_url": blob.public_url
        })

    except Exception as e:
        logger.exception("🔥 Exception during remix process")
        return jsonify({"error": str(e)}), 500

    finally:
        for f in [instrumental_input, vocals_input, remix_path]:
            if os.path.exists(f):
                os.remove(f)
        for d in [instrumental_dir, vocals_dir]:
            if os.path.exists(d):
                subprocess.run(["rm", "-rf", d])

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(debug=True, host="0.0.0.0", port=port)
