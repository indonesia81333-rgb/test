import os
import sys
import time
import math
import asyncio
import logging
from typing import Union
from mimetypes import guess_type

try:
    from pyrogram import Client, filters
    from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
    from pyrogram.errors import FloodWait
    import boto3
    from boto3.s3.transfer import TransferConfig
    from botocore.exceptions import NoCredentialsError, ClientError
except ImportError as e:
    print(f"Missing dependency: {e}. Please install requirements: pip install pyrogram tgcrypto boto3")
    sys.exit(1)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

try:
    # Fixed: changed 'cofing' to 'config'
    from config import config
    logger.info("Successfully imported configuration from 'config' module.")
except ImportError:
    config = None
    logger.warning("'config' module not found. Falling back to system environment variables.")

def get_config(key: str, default: str = None) -> Union[str, None]:
    """Helper function to extract config values from config module or system environment."""
    if config is not None:
        # Check if config is a dictionary
        if isinstance(config, dict) and key in config:
            return config[key]
        # Check if config is an object/class with attributes
        elif hasattr(config, key):
            return getattr(config, key)
    # Fallback to system environment variables
    return os.environ.get(key, default)

API_ID = get_config("API_ID")
API_HASH = get_config("API_HASH")
BOT_TOKEN = get_config("BOT_TOKEN")

WASABI_ACCESS_KEY = get_config("WASABI_ACCESS_KEY")
WASABI_SECRET_KEY = get_config("WASABI_SECRET_KEY")
WASABI_BUCKET = get_config("WASABI_BUCKET")
WASABI_REGION = get_config("WASABI_REGION", "us-east-1")

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

# Initialize standard Pyrogram Client
bot = Client(
    "wasabi_bot",
    api_id=int(API_ID),
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

# Initialize boto3 S3 Client targeting Wasabi endpoint
s3_client = boto3.client(
    "s3",
    endpoint_url=WASABI_ENDPOINT,
    aws_access_key_id=WASABI_ACCESS_KEY,
    aws_secret_access_key=WASABI_SECRET_KEY,
    region_name=WASABI_REGION
)

# Optimizations for up to 4GB file uploads
S3_TRANSFER_CONFIG = TransferConfig(
    multipart_threshold=1024 * 1024 * 50,  # Threshold of 50MB
    max_concurrency=10,                    # Use 10 threads for higher concurrency speeds
    multipart_chunksize=1024 * 1024 * 15,  # Upload in 15MB chunks
    use_threads=True
)

def human_readable_size(size_in_bytes: int) -> str:
    """Converts bytes to human-readable units (KB, MB, GB)."""
    if size_in_bytes == 0:
        return "0 B"
    size_name = ("B", "KB", "MB", "GB", "TB")
    i = int(math.floor(math.log(size_in_bytes, 1024)))
    p = math.pow(1024, i)
    s = round(size_in_bytes / p, 2)
    return f"{s} {size_name[i]}"

def get_progress_bar(percentage: float, length: int = 10) -> str:
    """Generates an aesthetic filled-to-unfilled visual progress bar."""
    filled_length = int(round(length * percentage / 100))
    bar = "■" * filled_length + "□" * (length - filled_length)
    return bar

async def safe_edit_message(message: Message, text: str, reply_markup=None):
    """Edits message content safely, gracefully catching FloodWait limits."""
    try:
        await message.edit_text(text, reply_markup=reply_markup)
    except FloodWait as e:
        logger.warning(f"FloodWait encountered. Sleeping for {e.value} seconds.")
        await asyncio.sleep(e.value)
    except Exception as e:
        logger.error(f"Failed to edit message: {e}")

class ProgressCallbackManager:
    """Tracks transfers and posts periodic updates (speed, ETA, size) without blocking."""
    def __init__(self, message: Message, action_verb: str, total_size: int):
        self.message = message
        self.action_verb = action_verb
        self.total_size = total_size
        self.start_time = time.time()
        self.last_update_time = time.time()
        self.downloaded_uploaded = 0

    async def update_progress(self, current_bytes: int):
        """Prepares metadata and formats real-time metrics for update dispatch."""
        now = time.time()
        # Throttled update interval (3.5 seconds) to strictly respect Telegram limits
        if now - self.last_update_time < 3.5 and current_bytes < self.total_size:
            return

        self.last_update_time = now
        elapsed = now - self.start_time
        
        # Performance speed calculation
        speed = current_bytes / elapsed if elapsed > 0 else 0
        speed_str = f"{human_readable_size(int(speed))}/s"
        
        percentage = (current_bytes / self.total_size) * 100 if self.total_size > 0 else 0
        bar = get_progress_bar(percentage)
        
        # Time Arrival (ETA) calculation
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
        """S3 callback integration running asynchronously via threadsafe event loop execution."""
        self.downloaded_uploaded += bytes_amount
        asyncio.run_coroutine_threadsafe(
            self.update_progress(self.downloaded_uploaded),
            bot.loop
        )

@bot.on_message(filters.command("start") & filters.private)
async def start_handler(client: Client, message: Message):
    welcome_text = (
        "👋 **Welcome to the Ultra High-Speed Wasabi S3 Link Generator Bot!**\n\n"
        "Send me any file, video, photo, or document (up to 4GB supported) and "
        "I will instantly upload it to your secure **Wasabi Storage Bucket** and provide you with a direct download link.\n\n"
        "**Features:**\n"
        "• High-speed multi-threaded multipart transfers\n"
        "• Real-time speed and remaining time metrics\n"
        "• Completely non-blocking processing\n\n"
        "Simply send or forward any file here to begin."
    )
    await message.reply_text(welcome_text)

@bot.on_message(filters.command("help") & filters.private)
async def help_handler(client: Client, message: Message):
    help_text = (
        "ℹ️ **How to use this Bot:**\n\n"
        "1. **Upload File to S3:** Send any media/document directly. The bot will download, upload to S3, and provide a shareable download link.\n"
        "2. **Storage Details:** S3 resources are securely managed on your own Wasabi account utilizing designated regions."
    )
    await message.reply_text(help_text)

@bot.on_message(
    (filters.document | filters.video | filters.audio | filters.photo) & filters.private
)
async def media_handler(client: Client, message: Message):
    """Processes incoming file, performs download, and pushes to Wasabi S3."""
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
    local_filepath = os.path.join("./downloads", f"{time.time()}_{file_name}")
    
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
        
        s3_object_key = f"uploads/{time.time()}/{file_name}"
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
                ExpiresIn=604800  # 7 Days lifetime
            )
        )

        success_message = (
            "✅ **Upload Completed Successfully!**\n\n"
            f"📁 **File Name:** `{file_name}`\n"
            f"⚖️ **File Size:** {human_readable_size(file_size)}\n"
            f"🪣 **Bucket Target:** `{WASABI_BUCKET}`\n"
            f"⏱️ **Link Expiry:** 7 Days\n\n"
            f"🔗 **Download Link:** [Click to Download]({presigned_url})"
        )

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📥 Download File", url=presigned_url)]
        ])
        
        await safe_edit_message(status_msg, success_message, reply_markup=keyboard)

    except ClientError as e:
        logger.error(f"Wasabi S3 client failed: {e}")
        await safe_edit_message(status_msg, f"❌ Wasabi S3 Storage Error: `{str(e)}`")
    except Exception as e:
        logger.error(f"Unexpected processing failure: {e}")
        await safe_edit_message(status_msg, f"❌ Internal Error: `{str(e)}`")
    finally:
        # Guarantee cleanup of local file
        try:
            if os.path.exists(local_filepath):
                os.remove(local_filepath)
                logger.info(f"Cleaned up local file: {local_filepath}")
        except Exception as e:
            logger.error(f"Failed to delete local temporary file: {e}")

if __name__ == "__main__":
    logger.info("Initializing Telegram-to-Wasabi Core Bot Client...")
    try:
        bot.run()
    except Exception as error:
        logger.fatal(f"Bot failed to start: {error}")

# End of file
