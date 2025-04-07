from flask import Flask, request, jsonify
import os
import uuid
import subprocess
import requests
import logging
import firebase_admin
from firebase_admin import credentials, storage

# Setup
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
    logger.info(f"📥 Downloading from: {url}")
    r = requests.get(url, stream=True)
    with open(filename, 'wb') as f:
        for chunk in r.iter_content(1024):
            if chunk:
                f.write(chunk)
    logger.info(f"✅ Download complete: {filename}")

def convert_to_wav(input_mp3, output_wav):
    command = ["ffmpeg", "-y", "-i", input_mp3, output_wav]
    logger.info(f"🔄 Converting to WAV: {input_mp3} → {output_wav}")
    subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

def split_audio_with_spleeter(input_wav, output_dir):
    os.makedirs(output_dir, exist_ok=True)
    command = ["spleeter", "separate", "-p", "spleeter:2stems", "-o", output_dir, input_wav]
    logger.info(f"🎼 Running Spleeter: {' '.join(command)}")
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        raise Exception(f"Spleeter failed: {result.stderr}")

def merge_audio(instrumental_path, vocal_path, output_path):
    command = [
        "ffmpeg", "-y",
        "-i", instrumental_path,
        "-i", vocal_path,
        "-filter_complex", "[0:a][1:a]amix=inputs=2:duration=first:dropout_transition=3",
        output_path
    ]
    logger.info(f"🎛️ Merging with FFmpeg: {' '.join(command)}")
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        raise Exception(f"FFmpeg merge failed: {result.stderr}")

@app.route("/")
def home():
    return "🎶 Remix API is running!"

@app.route('/remix', methods=['POST'])
def remix():
    data = request.json
    instrumental_url = data.get("instrumental_url")
    vocals_url = data.get("vocals_url")

    if not instrumental_url or not vocals_url:
        return jsonify({"error": "Both URLs are required"}), 400

    session_id = str(uuid.uuid4())
    logger.info(f"🆔 Session ID: {session_id}")

    instr_mp3 = f"{session_id}_instr.mp3"
    voc_mp3 = f"{session_id}_vocals.mp3"
    instr_wav = f"{session_id}_instr.wav"
    voc_wav = f"{session_id}_vocals.wav"

    instr_out_dir = os.path.join(OUTPUT_DIR, f"instr_{session_id}")
    voc_out_dir = os.path.join(OUTPUT_DIR, f"vocals_{session_id}")
    remix_path = os.path.join(OUTPUT_DIR, f"{session_id}_remix.mp3")

    try:
        # Download both files
        download_file(instrumental_url, instr_mp3)
        download_file(vocals_url, voc_mp3)

        # Convert to WAV
        convert_to_wav(instr_mp3, instr_wav)
        convert_to_wav(voc_mp3, voc_wav)

        # Spleeter
        split_audio_with_spleeter(instr_wav, instr_out_dir)
        split_audio_with_spleeter(voc_wav, voc_out_dir)

        # Expected Spleeter output folders
        instr_base = os.path.splitext(os.path.basename(instr_wav))[0]
        voc_base = os.path.splitext(os.path.basename(voc_wav))[0]

        instrumental_out = os.path.join(instr_out_dir, instr_base, "accompaniment.wav")
        vocals_out = os.path.join(voc_out_dir, voc_base, "vocals.wav")

        if not os.path.exists(instrumental_out) or not os.path.exists(vocals_out):
            raise Exception("Spleeter output files missing")

        # Merge both audio
        merge_audio(instrumental_out, vocals_out, remix_path)

        # Upload to Firebase
        blob = bucket.blob(f"remixes/{os.path.basename(remix_path)}")
        blob.upload_from_filename(remix_path)
        blob.make_public()

        return jsonify({"remix_url": blob.public_url})

    except Exception as e:
        logger.exception("🔥 Remix generation failed")
        return jsonify({"error": str(e)}), 500

    finally:
        for f in [instr_mp3, voc_mp3, instr_wav, voc_wav, remix_path]:
            if os.path.exists(f):
                os.remove(f)
        for d in [instr_out_dir, voc_out_dir]:
            if os.path.exists(d):
                subprocess.run(["rm", "-rf", d])

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(debug=True, host="0.0.0.0", port=port)
