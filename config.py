import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Telegram Configuration
    API_ID = int(os.getenv("API_ID"))
    API_HASH = os.getenv("API_HASH")
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    
    # Wasabi Configuration
    WASABI_ACCESS_KEY = os.getenv("WASABI_ACCESS_KEY")
    WASABI_SECRET_KEY = os.getenv("WASABI_SECRET_KEY")
    WASABI_BUCKET = os.getenv("WASABI_BUCKET")
    WASABI_REGION = os.getenv("WASABI_REGION", "us-east-1")
    
    # Wasabi Endpoint URL
    WASABI_ENDPOINT = f"https://s3.{WASABI_REGION}.wasabisys.com"
    
    # File Configuration
    MAX_FILE_SIZE = 4 * 1024 * 1024 * 1024  # 4GB
    CHUNK_SIZE = 1024 * 1024  # 1MB chunks
    
    # Bot Configuration
    DOWNLOAD_DIR = "downloads"
    STREAM_EXPIRY = 3600  # 1 hour
    
    # Allowed file types (empty list = all files allowed)
    ALLOWED_EXTENSIONS = []  # Example: ['mp4', 'mkv', 'mp3', 'pdf']
