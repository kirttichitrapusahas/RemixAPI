import os
import uuid
import tempfile
import subprocess
from flask import Blueprint, request, jsonify
from firebase_admin import storage

download_mp3_bp = Blueprint('download_mp3', __name__)

@download_mp3_bp.route('/download_mp3', methods=['POST'])
def download_mp3():
    data = request.get_json()
    youtube_url = data.get('url')

    if not youtube_url:
        return jsonify({"error": "Missing 'url' in request body"}), 400

    try:
        temp_dir = tempfile.mkdtemp()
        output_path = os.path.join(temp_dir, f"{uuid.uuid4()}.mp3")

        # Download using yt-dlp
        subprocess.run([
            "yt-dlp",
            "-x", "--audio-format", "mp3",
            "-o", output_path,
            youtube_url
        ], check=True)

        # Find the actual file (yt-dlp may use a template path)
        mp3_file = next((f for f in os.listdir(temp_dir) if f.endswith(".mp3")), None)
        if not mp3_file:
            raise Exception("MP3 file not found after download")

        full_path = os.path.join(temp_dir, mp3_file)

        # Upload to Firebase Storage
        bucket = storage.bucket()
        blob = bucket.blob(f"downloads/{mp3_file}")
        blob.upload_from_filename(full_path)
        blob.make_public()

        return jsonify({"downloadUrl": blob.public_url})

    except subprocess.CalledProcessError as e:
        return jsonify({"error": f"yt-dlp failed: {str(e)}"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        if os.path.exists(temp_dir):
            for file in os.listdir(temp_dir):
                os.remove(os.path.join(temp_dir, file))
            os.rmdir(temp_dir)
