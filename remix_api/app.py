from flask import Flask, request, jsonify, send_from_directory
import os
import uuid
import subprocess
import requests

app = Flask(__name__)
OUTPUT_DIR = "outputs"
os.makedirs(OUTPUT_DIR, exist_ok=True)

def download_file(url, filename):
    r = requests.get(url, stream=True)
    with open(filename, 'wb') as f:
        for chunk in r.iter_content(chunk_size=1024):
            if chunk:
                f.write(chunk)

@app.route("/")
def home():
    return "🎶 Remix API is running on Render!"

@app.route('/remix', methods=['POST'])
def remix():
    data = request.json
    instrumental_url = data.get("instrumental_url")
    vocals_url = data.get("vocals_url")

    if not instrumental_url or not vocals_url:
        return jsonify({"error": "Both URLs are required"}), 400

    session_id = str(uuid.uuid4())
    instrumental_path = f"{session_id}_instr.mp3"
    vocals_path = f"{session_id}_vocals.mp3"
    remix_path = os.path.join(OUTPUT_DIR, f"{session_id}_remix.mp3")

    try:
        # Download audio files
        download_file(instrumental_url, instrumental_path)
        download_file(vocals_url, vocals_path)

        # Remix with FFmpeg
        command = f"ffmpeg -i {instrumental_path} -i {vocals_path} -filter_complex '[0:a][1:a]amix=inputs=2:duration=first' {remix_path}"
        subprocess.run(command, shell=True, check=True)

        return jsonify({
            "remix_url": f"/download/{os.path.basename(remix_path)}"
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        # Clean up temp input files
        if os.path.exists(instrumental_path): os.remove(instrumental_path)
        if os.path.exists(vocals_path): os.remove(vocals_path)

@app.route('/download/<filename>')
def download(filename):
     file_path = os.path.join(OUTPUT_DIR, filename)
    if os.path.exists(file_path):
        return send_file(file_path, as_attachment=True)
    else:
        return "File not found", 404

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(debug=True, host="0.0.0.0", port=port)
