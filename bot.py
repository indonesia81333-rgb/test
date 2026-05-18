import os
import sys
import time
import math
import asyncio
import logging
import threading
from typing import Union
from mimetypes import guess_type
from flask import Flask, render_template, jsonify, request, send_file
from werkzeug.utils import secure_filename

try:
    from pyrogram import Client, filters
    from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
    from pyrogram.errors import FloodWait
    import boto3
    from boto3.s3.transfer import TransferConfig
    from botocore.exceptions import NoCredentialsError, ClientError
except ImportError as e:
    print(f"Missing dependency: {e}. Please install requirements: pip install pyrogram tgcrypto boto3 flask")
    sys.exit(1)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

try:
    from config import config
    logger.info("Successfully imported configuration from 'config' module.")
except ImportError:
    config = None
    logger.warning("'config' module not found. Falling back to system environment variables.")

def get_config(key: str, default: str = None) -> Union[str, None]:
    """Helper function to extract config values from config module or system environment."""
    if config is not None:
        if isinstance(config, dict) and key in config:
            return config[key]
        elif hasattr(config, key):
            return getattr(config, key)
    return os.environ.get(key, default)

# Telegram Configuration
API_ID = get_config("API_ID")
API_HASH = get_config("API_HASH")
BOT_TOKEN = get_config("BOT_TOKEN")

# Wasabi Configuration
WASABI_ACCESS_KEY = get_config("WASABI_ACCESS_KEY")
WASABI_SECRET_KEY = get_config("WASABI_SECRET_KEY")
WASABI_BUCKET = get_config("WASABI_BUCKET")
WASABI_REGION = get_config("WASABI_REGION", "us-east-1")

# Flask Configuration
FLASK_PORT = int(get_config("FLASK_PORT", 8000))
FLASK_HOST = get_config("FLASK_HOST", "0.0.0.0")

# Verify essential credentials
missing_vars = []
if not API_ID: missing_vars.append("API_ID")
if not API_HASH: missing_vars.append("API_HASH")
if not BOT_TOKEN: missing_vars.append("BOT_TOKEN")
if not WASABI_ACCESS_KEY: missing_vars.append("WASABI_ACCESS_KEY")
if not WASABI_SECRET_KEY: missing_vars.append("WASABI_SECRET_KEY")
if not WASABI_BUCKET: missing_vars.append("WASABI_BUCKET")

if missing_vars:
    logger.error(f"Missing environment variables: {', '.join(missing_vars)}")
    sys.exit(1)

WASABI_ENDPOINT = f"https://s3.{WASABI_REGION}.wasabisys.com"

# Initialize Flask app
flask_app = Flask(__name__, template_folder="templates")
flask_app.config['MAX_CONTENT_LENGTH'] = 4 * 1024 * 1024 * 1024  # 4GB max file size

# Initialize Pyrogram Client
bot = Client(
    "wasabi_bot",
    api_id=int(API_ID),
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

# Initialize boto3 S3 Client
s3_client = boto3.client(
    "s3",
    endpoint_url=WASABI_ENDPOINT,
    aws_access_key_id=WASABI_ACCESS_KEY,
    aws_secret_access_key=WASABI_SECRET_KEY,
    region_name=WASABI_REGION
)

# S3 Transfer Configuration
S3_TRANSFER_CONFIG = TransferConfig(
    multipart_threshold=1024 * 1024 * 50,
    max_concurrency=10,
    multipart_chunksize=1024 * 1024 * 15,
    use_threads=True
)

def human_readable_size(size_in_bytes: int) -> str:
    """Converts bytes to human-readable units."""
    if size_in_bytes == 0:
        return "0 B"
    size_name = ("B", "KB", "MB", "GB", "TB")
    i = int(math.floor(math.log(size_in_bytes, 1024)))
    p = math.pow(1024, i)
    s = round(size_in_bytes / p, 2)
    return f"{s} {size_name[i]}"

def get_progress_bar(percentage: float, length: int = 10) -> str:
    """Generates an aesthetic progress bar."""
    filled_length = int(round(length * percentage / 100))
    bar = "■" * filled_length + "□" * (length - filled_length)
    return bar

async def safe_edit_message(message: Message, text: str, reply_markup=None):
    """Edits message content safely."""
    try:
        await message.edit_text(text, reply_markup=reply_markup)
    except FloodWait as e:
        logger.warning(f"FloodWait encountered. Sleeping for {e.value} seconds.")
        await asyncio.sleep(e.value)
    except Exception as e:
        logger.error(f"Failed to edit message: {e}")

class ProgressCallbackManager:
    """Tracks transfers and posts periodic updates."""
    def __init__(self, message: Message, action_verb: str, total_size: int):
        self.message = message
        self.action_verb = action_verb
        self.total_size = total_size
        self.start_time = time.time()
        self.last_update_time = time.time()
        self.downloaded_uploaded = 0

    async def update_progress(self, current_bytes: int):
        """Prepares metadata and formats real-time metrics."""
        now = time.time()
        if now - self.last_update_time < 3.5 and current_bytes < self.total_size:
            return

        self.last_update_time = now
        elapsed = now - self.start_time
        
        speed = current_bytes / elapsed if elapsed > 0 else 0
        speed_str = f"{human_readable_size(int(speed))}/s"
        
        percentage = (current_bytes / self.total_size) * 100 if self.total_size > 0 else 0
        bar = get_progress_bar(percentage)
        
        if speed > 0:
            eta_seconds = (self.total_size - current_bytes) / speed
            eta_str = f"{int(eta_seconds // 60)}m {int(eta_seconds % 60)}s" if eta_seconds > 60 else f"{int(eta_seconds)}s"
        else:
            eta_str = "Calculating..."
            
        progress_text = (
            f"**⚡ {self.action_verb}...**\n\n"
            f"┌ **Progress:** {bar} {percentage:.1f}%\n"
            f"├ **Size:** {human_readable_size(current_bytes)} / {human_readable_size(self.total_size)}\n"
            f"├ **Speed:** {speed_str}\n"
            f"└ **ETA:** {eta_str}"
        )
        
        loop = asyncio.get_event_loop()
        loop.create_task(safe_edit_message(self.message, progress_text))

    def s3_callback(self, bytes_amount: int):
        """S3 callback integration."""
        self.downloaded_uploaded += bytes_amount
        asyncio.run_coroutine_threadsafe(
            self.update_progress(self.downloaded_uploaded),
            bot.loop
        )

# Flask Routes
@flask_app.route("/")
def index():
    """Render main file manager interface."""
    return render_template("index.html")

@flask_app.route("/health")
def health():
    """Health check endpoint."""
    return jsonify({"status": "ok", "service": "wasabi-telegram-bot"})

@flask_app.route("/api/files")
def list_files():
    """List all files in the Wasabi bucket."""
    try:
        prefix = request.args.get('prefix', 'uploads/')
        continuation_token = request.args.get('continuation_token', None)
        
        list_kwargs = {
            'Bucket': WASABI_BUCKET,
            'Prefix': prefix,
            'MaxKeys': 50
        }
        
        if continuation_token:
            list_kwargs['ContinuationToken'] = continuation_token
            
        response = s3_client.list_objects_v2(**list_kwargs)
        
        files = []
        if 'Contents' in response:
            for obj in response['Contents']:
                files.append({
                    'key': obj['Key'],
                    'size': obj['Size'],
                    'size_human': human_readable_size(obj['Size']),
                    'last_modified': obj['LastModified'].isoformat(),
                    'filename': os.path.basename(obj['Key'])
                })
        
        return jsonify({
            'files': files,
            'has_more': response.get('IsTruncated', False),
            'continuation_token': response.get('NextContinuationToken')
        })
    except Exception as e:
        logger.error(f"Error listing files: {e}")
        return jsonify({'error': str(e)}), 500

@flask_app.route("/api/generate-link", methods=['POST'])
def generate_link():
    """Generate a presigned URL for a specific file."""
    try:
        data = request.get_json()
        file_key = data.get('key')
        expires_in = int(data.get('expires_in', 604800))  # Default 7 days
        
        if not file_key:
            return jsonify({'error': 'File key is required'}), 400
        
        # Validate file exists
        try:
            s3_client.head_object(Bucket=WASABI_BUCKET, Key=file_key)
        except ClientError as e:
            if e.response['Error']['Code'] == '404':
                return jsonify({'error': 'File not found'}), 404
            raise
        
        # Generate presigned URL
        presigned_url = s3_client.generate_presigned_url(
            ClientMethod='get_object',
            Params={'Bucket': WASABI_BUCKET, 'Key': file_key},
            ExpiresIn=expires_in
        )
        
        return jsonify({
            'url': presigned_url,
            'expires_in': expires_in,
            'expires_in_human': f"{expires_in // 86400} days" if expires_in >= 86400 else f"{expires_in // 3600} hours"
        })
    except Exception as e:
        logger.error(f"Error generating link: {e}")
        return jsonify({'error': str(e)}), 500

@flask_app.route("/api/delete-file", methods=['DELETE'])
def delete_file():
    """Delete a file from the Wasabi bucket."""
    try:
        data = request.get_json()
        file_key = data.get('key')
        
        if not file_key:
            return jsonify({'error': 'File key is required'}), 400
        
        s3_client.delete_object(Bucket=WASABI_BUCKET, Key=file_key)
        
        return jsonify({'message': 'File deleted successfully'})
    except Exception as e:
        logger.error(f"Error deleting file: {e}")
        return jsonify({'error': str(e)}), 500

@flask_app.route("/api/bucket-info")
def bucket_info():
    """Get bucket information and statistics."""
    try:
        # Get bucket size and file count
        total_size = 0
        file_count = 0
        
        paginator = s3_client.get_paginator('list_objects_v2')
        for page in paginator.paginate(Bucket=WASABI_BUCKET):
            if 'Contents' in page:
                file_count += len(page['Contents'])
                total_size += sum(obj['Size'] for obj in page['Contents'])
        
        return jsonify({
            'bucket_name': WASABI_BUCKET,
            'region': WASABI_REGION,
            'file_count': file_count,
            'total_size': total_size,
            'total_size_human': human_readable_size(total_size)
        })
    except Exception as e:
        logger.error(f"Error getting bucket info: {e}")
        return jsonify({'error': str(e)}), 500

# Telegram Bot Handlers
@bot.on_message(filters.command("start") & filters.private)
async def start_handler(client: Client, message: Message):
    welcome_text = (
        "👋 **Welcome to the Ultra High-Speed Wasabi S3 Link Generator Bot!**\n\n"
        "Send me any file, video, photo, or document (up to 4GB supported) and "
        "I will instantly upload it to your secure **Wasabi Storage Bucket** and provide you with a direct download link.\n\n"
        "**Features:**\n"
        "• High-speed multi-threaded multipart transfers\n"
        "• Real-time speed and remaining time metrics\n"
        "• Web interface for file management\n\n"
        f"🌐 **Web Interface:** http://localhost:{FLASK_PORT}\n\n"
        "Simply send or forward any file here to begin."
    )
    await message.reply_text(welcome_text)

@bot.on_message(filters.command("help") & filters.private)
async def help_handler(client: Client, message: Message):
    help_text = (
        "ℹ️ **How to use this Bot:**\n\n"
        "1. **Upload File to S3:** Send any media/document directly\n"
        "2. **Manage Files:** Visit the web interface to view, download, or delete files\n"
        "3. **Generate Links:** Create shareable download links with custom expiry times\n\n"
        f"**Web Interface:** http://localhost:{FLASK_PORT}"
    )
    await message.reply_text(help_text)

@bot.on_message(
    (filters.document | filters.video | filters.audio | filters.photo) & filters.private
)
async def media_handler(client: Client, message: Message):
    """Processes incoming file and uploads to Wasabi S3."""
    media_obj = None
    file_name = "unknown_file"
    
    if message.document:
        media_obj = message.document
        file_name = message.document.file_name
    elif message.video:
        media_obj = message.video
        file_name = message.video.file_name or f"video_{message.video.file_unique_id}.mp4"
    elif message.audio:
        media_obj = message.audio
        file_name = message.audio.file_name or f"audio_{message.audio.file_unique_id}.mp3"
    elif message.photo:
        media_obj = message.photo
        file_name = f"photo_{message.photo.file_unique_id}.jpg"
        
    if not media_obj:
        await message.reply_text("❌ Unsupported file type or file reference could not be resolved.")
        return

    file_size = getattr(media_obj, "file_size", 0)
    if not file_size and isinstance(media_obj, list):
        media_obj = media_obj[-1]
        file_size = media_obj.file_size
        
    status_msg = await message.reply_text("⏳ Preparing to download from Telegram servers...")
    
    os.makedirs("./downloads", exist_ok=True)
    local_filepath = os.path.join("./downloads", f"{time.time()}_{secure_filename(file_name)}")
    
    progress_manager = ProgressCallbackManager(status_msg, "Downloading from Telegram", file_size)

    async def telegram_progress_adapter(current, total):
        await progress_manager.update_progress(current)

    try:
        download_path = await client.download_media(
            message=media_obj,
            file_name=local_filepath,
            progress=telegram_progress_adapter
        )
        
        if not download_path or not os.path.exists(download_path):
            await safe_edit_message(status_msg, "❌ Failed to download file from Telegram.")
            return

        await safe_edit_message(status_msg, "⏳ Connecting to Wasabi Storage...")
        
        s3_object_key = f"uploads/{time.strftime('%Y/%m/%d')}/{int(time.time())}_{secure_filename(file_name)}"
        upload_progress_manager = ProgressCallbackManager(status_msg, "Uploading to Wasabi S3", file_size)
        
        content_type, _ = guess_type(local_filepath)
        extra_args = {}
        if content_type:
            extra_args["ContentType"] = content_type

        loop = asyncio.get_running_loop()
        await safe_edit_message(status_msg, "🚀 Negotiating multi-part upload pipeline...")
        
        await loop.run_in_executor(
            None,
            lambda: s3_client.upload_file(
                Filename=local_filepath,
                Bucket=WASABI_BUCKET,
                Key=s3_object_key,
                Config=S3_TRANSFER_CONFIG,
                ExtraArgs=extra_args,
                Callback=upload_progress_manager.s3_callback
            )
        )
        
        await safe_edit_message(status_msg, "🔗 Generating direct secure download link...")
        
        presigned_url = await loop.run_in_executor(
            None,
            lambda: s3_client.generate_presigned_url(
                ClientMethod="get_object",
                Params={"Bucket": WASABI_BUCKET, "Key": s3_object_key},
                ExpiresIn=604800
            )
        )

        success_message = (
            "✅ **Upload Completed Successfully!**\n\n"
            f"📁 **File Name:** `{file_name}`\n"
            f"⚖️ **File Size:** {human_readable_size(file_size)}\n"
            f"🪣 **Bucket Target:** `{WASABI_BUCKET}`\n"
            f"🔑 **File Key:** `{s3_object_key}`\n"
            f"⏱️ **Link Expiry:** 7 Days\n\n"
            f"🔗 **Download Link:** [Click to Download]({presigned_url})\n\n"
            f"🌐 **Manage in Web UI:** http://localhost:{FLASK_PORT}"
        )

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📥 Download File", url=presigned_url)],
            [InlineKeyboardButton("🌐 Open Web Interface", url=f"http://localhost:{FLASK_PORT}")]
        ])
        
        await safe_edit_message(status_msg, success_message, reply_markup=keyboard)

    except ClientError as e:
        logger.error(f"Wasabi S3 client failed: {e}")
        await safe_edit_message(status_msg, f"❌ Wasabi S3 Storage Error: `{str(e)}`")
    except Exception as e:
        logger.error(f"Unexpected processing failure: {e}")
        await safe_edit_message(status_msg, f"❌ Internal Error: `{str(e)}`")
    finally:
        try:
            if os.path.exists(local_filepath):
                os.remove(local_filepath)
                logger.info(f"Cleaned up local file: {local_filepath}")
        except Exception as e:
            logger.error(f"Failed to delete local temporary file: {e}")

def run_flask():
    """Run Flask app in a separate thread."""
    flask_app.run(host=FLASK_HOST, port=FLASK_PORT, debug=False, use_reloader=False)

def run_bot():
    """Run the Telegram bot."""
    bot.run()

if __name__ == "__main__":
    logger.info("Initializing Telegram-to-Wasabi Bot with Web Interface...")
    
    # Run Flask in a separate thread
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    logger.info(f"Flask web interface running on http://{FLASK_HOST}:{FLASK_PORT}")
    
    # Run the bot in the main thread
    try:
        run_bot()
    except Exception as error:
        logger.fatal(f"Bot failed to start: {error}")

# End of file
