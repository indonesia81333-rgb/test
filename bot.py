from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.enums import ParseMode
from pyrogram.errors import FloodWait
import os
import asyncio
import hashlib
from datetime import datetime
from config import Config
from utils.wasabi_handler import WasabiHandler
from utils.keyboards import get_main_keyboard, get_file_keyboard
from utils.file_utils import get_file_type, format_file_size

# Initialize bot and storage
app = Client("telegram_wasabi_bot", api_id=Config.API_ID, api_hash=Config.API_HASH, bot_token=Config.BOT_TOKEN)
wasabi = WasabiHandler()

# Store user file mappings (in production, use database)
user_files = {}

async def progress_callback(current, total, message, operation):
    """Handle upload/download progress"""
    try:
        percent = (current * 100) / total
        progress_bar = "▓" * int(percent // 2) + "░" * (50 - int(percent // 2))
        text = f"**{operation} Progress:** `{percent:.1f}%`\n"
        text += f"**[{progress_bar}]**\n"
        text += f"**Transferred:** `{format_file_size(current)}` / `{format_file_size(total)}`"
        
        await message.edit_text(text)
    except Exception as e:
        print(f"Progress update error: {e}")

@app.on_message(filters.command("start"))
async def start_command(client: Client, message: Message):
    """Handle /start command"""
    welcome_text = """
**🎬 Welcome to Telegram File Bot with Wasabi Cloud Storage!**

I can handle files up to **4GB** with cloud storage integration.

**📋 Available Commands:**
• `/upload` - Upload files (or just send any file)
• `/list` - List all stored files  
• `/test` - Test Wasabi connection
• `/help` - Show detailed help

**💡 Features:**
• 4GB file support
• Direct streaming to MX Player/VLC
• Cloud storage with Wasabi
• Mobile optimized
• Real-time progress tracking

Just send me any file to get started!
"""
    await message.reply_text(welcome_text, reply_markup=get_main_keyboard())

@app.on_message(filters.command("help"))
async def help_command(client: Client, message: Message):
    """Handle /help command"""
    help_text = """
**📚 Detailed Help Guide**

**📤 Uploading Files:**
• Use `/upload` or simply send any file
• Supports up to 4GB files
• Real-time progress updates
• Files stored securely on Wasabi

**📥 Downloading Files:**
• Use `/list` to see all files
• Click download button next to file
• Direct download links provided

**🎥 Streaming:**
• Use `/list` to browse files
• Click "Stream" for video/audio files
• One-click launch in MX Player or VLC
• Get web player link with `/web <file_id>`

**🔗 File IDs:**
Each file gets a unique ID. Use with:
• `/download <file_id>` - Download file
• `/stream <file_id>` - Get stream link
• `/web <file_id>` - Web player

**⚠️ Notes:**
• Stream links expire in 1 hour
• Max file size: 4GB
• Optimized for mobile devices
"""
    await message.reply_text(help_text, reply_markup=get_main_keyboard())

@app.on_message(filters.command("upload"))
async def upload_command(client: Client, message: Message):
    """Handle /upload command"""
    await message.reply_text(
        "📤 **Send me any file you want to upload!**\n\n"
        "• Maximum size: 4GB\n"
        "• Supported: Documents, videos, audio, photos\n"
        "• Files will be stored securely on Wasabi cloud\n\n"
        "Just send the file now."
    )

@app.on_message(filters.command("list"))
async def list_files_command(client: Client, message: Message):
    """Handle /list command - show all files"""
    list_msg = await message.reply_text("📋 **Fetching file list...**")
    
    files = await wasabi.list_files()
    
    if not files:
        await list_msg.edit_text("❌ **No files found in storage!**\n\nUpload files using /upload")
        return
    
    text = "**📁 Your Stored Files:**\n\n"
    for i, file in enumerate(files[:20], 1):  # Show first 20 files
        file_id = hashlib.md5(file['key'].encode()).hexdigest()[:16]
        user_files[file_id] = file['key']
        
        text += f"{i}. **{os.path.basename(file['key'])}**\n"
        text += f"   📦 Size: `{format_file_size(file['size'])}`\n"
        text += f"   🆔 ID: `{file_id}`\n\n"
    
    if len(files) > 20:
        text += f"_And {len(files) - 20} more files..._"
    
    await list_msg.edit_text(text)
    
    # Send as separate message with keyboard for first 5 files
    keyboard = []
    for i, file in enumerate(files[:5]):
        file_id = hashlib.md5(file['key'].encode()).hexdigest()[:16]
        keyboard.append([
            InlineKeyboardButton(f"📥 {os.path.basename(file['key'])[:20]}", callback_data=f"file_{file_id}")
        ])
    
    keyboard.append([InlineKeyboardButton("🔄 Refresh", callback_data="refresh_list")])
    
    await client.send_message(
        message.chat.id,
        "**🎯 Quick Access:**\nTap a file below to see options:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

@app.on_message(filters.command("test"))
async def test_command(client: Client, message: Message):
    """Test Wasabi connection"""
    test_msg = await message.reply_text("🔄 **Testing Wasabi connection...**")
    
    if await wasabi.test_connection():
        await test_msg.edit_text("✅ **Wasabi connection successful!**\n\nCloud storage is ready for use.")
    else:
        await test_msg.edit_text("❌ **Wasabi connection failed!**\n\nPlease check your credentials and bucket settings.")

@app.on_message(filters.command("download"))
async def download_command(client: Client, message: Message):
    """Handle /download command with file ID"""
    parts = message.text.split(maxsplit=1)
    
    if len(parts) < 2:
        await message.reply_text("❌ **Please provide a file ID!**\n\nUsage: `/download <file_id>`")
        return
    
    file_id = parts[1].strip()
    
    if file_id not in user_files:
        await message.reply_text("❌ **Invalid file ID!**\n\nUse `/list` to get valid file IDs.")
        return
    
    file_key = user_files[file_id]
    file_name = os.path.basename(file_key)
    
    download_msg = await message.reply_text(f"🔄 **Downloading:** `{file_name}`\n\nStarting download...")
    
    download_path = os.path.join(Config.DOWNLOAD_DIR, file_name)
    os.makedirs(Config.DOWNLOAD_DIR, exist_ok=True)
    
    result = await wasabi.download_file(
        file_key, 
        download_path,
        lambda p: asyncio.create_task(progress_callback(p, 100, download_msg, "Downloading"))
    )
    
    if result["success"]:
        await download_msg.edit_text(f"✅ **Download complete!**\n\n📁 File: `{file_name}`\n📦 Size: `{format_file_size(result['size'])}`\n\nSending file...")
        
        # Send file to user
        await client.send_document(
            message.chat.id,
            download_path,
            caption=f"📥 **{file_name}**\n📦 Size: {format_file_size(result['size'])}",
            progress=lambda c, t: asyncio.create_task(progress_callback(c, t, download_msg, "Uploading to Telegram"))
        )
        
        # Clean up
        os.remove(download_path)
        await download_msg.delete()
    else:
        await download_msg.edit_text(f"❌ **Download failed!**\n\nError: {result.get('error', 'Unknown error')}")

@app.on_message(filters.command("stream"))
async def stream_command(client: Client, message: Message):
    """Get streaming link for a file"""
    parts = message.text.split(maxsplit=1)
    
    if len(parts) < 2:
        await message.reply_text("❌ **Please provide a file ID!**\n\nUsage: `/stream <file_id>`")
        return
    
    file_id = parts[1].strip()
    
    if file_id not in user_files:
        await message.reply_text("❌ **Invalid file ID!**\n\nUse `/list` to get valid file IDs.")
        return
    
    file_key = user_files[file_id]
    file_name = os.path.basename(file_key)
    file_type = get_file_type(file_name)
    
    if file_type not in ["video", "audio"]:
        await message.reply_text("❌ **This file type cannot be streamed!**\n\nOnly video and audio files are supported for streaming.")
        return
    
    url = wasabi.generate_presigned_url(file_key)
    
    if url:
        stream_text = f"""
**🎥 Streaming Link Ready!**

**📁 File:** `{file_name}`
**📱 Open in MX Player:** `{url}`
**🎬 Open in VLC:** `{url}`

**📲 Mobile Users:**
1. Tap the link above
2. Select "Open with MX Player" or VLC
3. Enjoy streaming!

**⚠️ Link expires in 1 hour**
"""
        await message.reply_text(stream_text)
    else:
        await message.reply_text("❌ **Failed to generate streaming link!**")

@app.on_message(filters.command("web"))
async def web_command(client: Client, message: Message):
    """Get web player interface link"""
    parts = message.text.split(maxsplit=1)
    
    if len(parts) < 2:
        await message.reply_text("❌ **Please provide a file ID!**\n\nUsage: `/web <file_id>`")
        return
    
    file_id = parts[1].strip()
    
    if file_id not in user_files:
        await message.reply_text("❌ **Invalid file ID!**\n\nUse `/list` to get valid file IDs.")
        return
    
    file_key = user_files[file_id]
    file_name = os.path.basename(file_key)
    
    url = wasabi.generate_presigned_url(file_key)
    
    if url:
        web_player_url = f"https://your-domain.com/player.html?url={url}"
        
        web_text = f"""
**🌐 Web Player Interface**

**📁 File:** `{file_name}`

**🔗 Web Player Link:** `{web_player_url}`

**📱 Mobile Instructions:**
1. Open the link in any browser
2. Video will play in HTML5 player
3. Works on iOS, Android, and desktop

**⚠️ Link expires in 1 hour**
"""
        await message.reply_text(web_text)
    else:
        await message.reply_text("❌ **Failed to generate web player link!**")

@app.on_message(filters.document | filters.video | filters.audio | filters.photo)
async def handle_file_upload(client: Client, message: Message):
    """Handle direct file uploads"""
    
    # Check file size
    file_size = 0
    file_obj = None
    
    if message.document:
        file_obj = message.document
        file_size = file_obj.file_size
    elif message.video:
        file_obj = message.video
        file_size = file_obj.file_size
    elif message.audio:
        file_obj = message.audio
        file_size = file_obj.file_size
    elif message.photo:
        file_obj = message.photo[-1]
        file_size = file_obj.file_size
    
    if file_size > Config.MAX_FILE_SIZE:
        await message.reply_text(f"❌ **File too large!**\n\nMaximum allowed: 4GB\nYour file: {format_file_size(file_size)}")
        return
    
    upload_msg = await message.reply_text(f"🔄 **Processing your file...**\n\n📁 Downloading from Telegram...")
    
    # Download file from Telegram
    file_path = await client.download_media(
        message,
        file_name=f"{message.from_user.id}_{file_obj.file_id}",
        progress=lambda c, t: asyncio.create_task(progress_callback(c, t, upload_msg, "Downloading"))
    )
    
    if not file_path:
        await upload_msg.edit_text("❌ **Failed to download file from Telegram!**")
        return
    
    await upload_msg.edit_text(f"📤 **Uploading to Wasabi cloud...**\n\n📁 File ready for cloud storage...")
    
    # Generate unique file key
    file_key = f"uploads/{message.from_user.id}/{datetime.now().strftime('%Y%m%d_%H%M%S')}_{os.path.basename(file_path)}"
    
    # Upload to Wasabi
    result = await wasabi.upload_file(
        file_path,
        file_key,
        lambda p: asyncio.create_task(progress_callback(p, 100, upload_msg, "Uploading to Wasabi"))
    )
    
    if result["success"]:
        file_id = hashlib.md5(file_key.encode()).hexdigest()[:16]
        user_files[file_id] = file_key
        
        # Get file type for appropriate keyboard
        file_type = get_file_type(file_path)
        
        await upload_msg.edit_text(
            f"✅ **File uploaded successfully!**\n\n"
            f"📁 **File:** `{os.path.basename(file_path)}`\n"
            f"📦 **Size:** `{format_file_size(file_size)}`\n"
            f"🆔 **File ID:** `{file_id}`\n\n"
            f"Use the buttons below to access your file:",
            reply_markup=get_file_keyboard(file_id, file_type)
        )
        
        # Clean up
        os.remove(file_path)
    else:
        await upload_msg.edit_text(f"❌ **Upload failed!**\n\nError: {result.get('error', 'Unknown error')}")
        os.remove(file_path)

@app.on_callback_query()
async def handle_callbacks(client: Client, callback_query: CallbackQuery):
    """Handle button callbacks"""
    data = callback_query.data
    
    if data.startswith("file_"):
        file_id = data[5:]
        if file_id in user_files:
            file_key = user_files[file_id]
            file_name = os.path.basename(file_key)
            file_type = get_file_type(file_name)
            
            await callback_query.message.reply_text(
                f"**📁 File Options:**\n\n**Name:** `{file_name}`\n**ID:** `{file_id}`\n\nChoose an action:",
                reply_markup=get_file_keyboard(file_id, file_type)
            )
    
    elif data.startswith("download_"):
        file_id = data[9:]
        if file_id in user_files:
            await download_command(client, callback_query.message)
    
    elif data.startswith("stream_"):
        file_id = data[7:]
        if file_id in user_files:
            await stream_command(client, callback_query.message)
    
    elif data == "refresh_list":
        await list_files_command(client, callback_query.message)
    
    await callback_query.answer()

if __name__ == "__main__":
    print("🚀 Starting Telegram File Bot with Wasabi Cloud Storage...")
    print("📋 Bot is running and ready for commands!")
    app.run()
