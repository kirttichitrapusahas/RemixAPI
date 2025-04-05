from flask import Flask, request, jsonify, send_file
import os
import uuid
import subprocess
import requests
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
OUTPUT_DIR = "outputs"
os.makedirs(OUTPUT_DIR, exist_ok=True)

def download_file(url, filename):
    logger.info(f"Downloading from: {url} -> {filename}")
    r = requests.get(url, stream=True)
    with open(filename, 'wb') as f:
        for chunk in r.iter_content(chunk_size=1024):
            if chunk:
                f.write(chunk)
    logger.info(f"Download complete: {filename}")

@app.route("/")
def home():
    return "🎶 Remix API is running on Render!"

@app.route('/remix', methods=['POST'])
def remix():
    data = request.json
    instrumental_url = data.get("instrumental_url")
    vocals_url = data.get("vocals_url")

    if not instrumental_url or not vocals_url:
        logger.error("Missing URL(s) in request")
        return jsonify({"error": "Both URLs are required"}), 400

    session_id = str(uuid.uuid4())
    instrumental_path = f"{session_id}_instr.mp3"
    vocals_path = f"{session_id}_vocals.mp3"
    remix_path = os.path.join(OUTPUT_DIR, f"{session_id}_remix.mp3")

    try:
        logger.info(f"Session ID: {session_id}")
        download_file(instrumental_url, instrumental_path)
        download_file(vocals_url, vocals_path)

        command = f"ffmpeg -i {instrumental_path} -i {vocals_path} -filter_complex '[0:a][1:a]amix=inputs=2:duration=first' {remix_path}"
        logger.info(f"Running FFmpeg command: {command}")

        result = subprocess.run(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        logger.info(f"FFmpeg stdout: {result.stdout.decode()}")
        logger.info(f"FFmpeg stderr: {result.stderr.decode()}")

        if result.returncode != 0:
            logger.error("FFmpeg failed")
            return jsonify({"error": "Remix failed", "details": result.stderr.decode()}), 500

        if not os.path.exists(remix_path):
            logger.error("Remix file not created")
            return jsonify({"error": "Remix file was not created"}), 500

        logger.info(f"Remix successfully created: {remix_path}")
        remix_url = f"/download/{os.path.basename(remix_path)}"
        return jsonify({"remix_url": remix_url})

    except Exception as e:
        logger.exception("Exception during remix process")
        return jsonify({"error": str(e)}), 500

    finally:
        if os.path.exists(instrumental_path): os.remove(instrumental_path)
        if os.path.exists(vocals_path): os.remove(vocals_path)

@app.route('/download/<filename>')
def download(filename):
    file_path = os.path.join(OUTPUT_DIR, filename)
    logger.info(f"Download request: {file_path}")
    if os.path.exists(file_path):
        return send_file(file_path, mimetype="audio/mpeg", as_attachment=True)
    else:
        logger.warning("Requested file not found")
        return "File not found", 404

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    logger.info(f"Starting Remix API on port {port}")
    app.run(debug=False, host="0.0.0.0", port=port)
