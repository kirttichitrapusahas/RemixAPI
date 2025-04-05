import os
import uuid
import tempfile
import subprocess
import logging
from flask import Blueprint, request, jsonify
from firebase_admin import storage

# Configure logger
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

download_mp3_bp = Blueprint('download_mp3', __name__)

@download_mp3_bp.route('/download_mp3', methods=['POST'])
def download_mp3():
    logger.info("🎧 Received request to /download_mp3")

    data = request.get_json()
    youtube_url = data.get('url')
    logger.info(f"🔗 YouTube URL received: {youtube_url}")

    if not youtube_url:
        logger.error("❌ Missing 'url' in request body")
        return jsonify({"error": "Missing 'url' in request body"}), 400

    temp_dir = None
    try:
        # Create temp dir
        temp_dir = tempfile.mkdtemp()
        logger.info(f"📁 Temporary directory created: {temp_dir}")

        output_path = os.path.join(temp_dir, f"{uuid.uuid4()}.mp3")
        logger.info(f"📥 Download path: {output_path}")

        # Download using yt-dlp
        logger.info("⬇️ Starting yt-dlp download")
        subprocess.run([
            "yt-dlp",
            "-x", "--audio-format", "mp3",
            "-o", output_path,
            youtube_url
        ], check=True)
        logger.info("✅ yt-dlp download completed")

        # Locate MP3 file
        mp3_file = next((f for f in os.listdir(temp_dir) if f.endswith(".mp3")), None)
        if not mp3_file:
            logger.error("❌ MP3 file not found after yt-dlp execution")
            raise Exception("MP3 file not found after download")

        full_path = os.path.join(temp_dir, mp3_file)
        logger.info(f"🎵 MP3 file located: {full_path}")

        # Upload to Firebase Storage
        bucket = storage.bucket()
        blob = bucket.blob(f"downloads/{mp3_file}")
        blob.upload_from_filename(full_path)
        blob.make_public()

        logger.info(f"🚀 Uploaded to Firebase Storage: {blob.public_url}")

        return jsonify({"downloadUrl": blob.public_url})

    except subprocess.CalledProcessError as e:
        logger.exception("❌ yt-dlp failed")
        return jsonify({"error": f"yt-dlp failed: {str(e)}"}), 500
    except Exception as e:
        logger.exception("❌ Unexpected error occurred")
        return jsonify({"error": str(e)}), 500
    finally:
        if temp_dir and os.path.exists(temp_dir):
            logger.info("🧹 Cleaning up temporary files")
            for file in os.listdir(temp_dir):
                file_path = os.path.join(temp_dir, file)
                os.remove(file_path)
                logger.debug(f"🗑️ Deleted: {file_path}")
            os.rmdir(temp_dir)
            logger.info(f"🗂️ Removed temp dir: {temp_dir}")
