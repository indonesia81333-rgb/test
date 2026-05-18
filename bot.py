from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
import os
import hashlib
from datetime import datetime
from config import Config
from utils.wasabi_handler import WasabiHandler
from utils.file_utils import get_file_type, format_file_size
from utils.keyboards import get_main_keyboard, get_file_keyboard

# Initialize bot and storage
app = Client(
    "telegram_wasabi_bot",
    api_id=Config.API_ID,
    api_hash=Config.API_HASH,
    bot_token=Config.BOT_TOKEN
)
wasabi = WasabiHandler()

# Store user file mappings
user_files = {}

@app.on_message(filters.command("start"))
async def start_command(client: Client, message: Message):
    """Handle /start command"""
    welcome_text = f"""
**🎬 Welcome to Telegram File Bot!**

Hi {message.from_user.first_name}! I can store your files on Wasabi cloud storage.

**✨ Features:**
• 📤 Upload files up to 4GB
• 📥 Download anytime
• 🎥 Stream videos/audio
• ☁️ Secure cloud storage
• 📱 Mobile optimized

**📋 Commands:**
/upload - Upload a file
/list - List all files
/test - Test connection
/help - Show help

Just send me any file to begin!
"""
    await message.reply_text(welcome_text, reply_markup=get_main_keyboard())

@app.on_message(filters.command("help"))
async def help_command(client: Client, message: Message):
    """Handle /help command"""
    help_text = """
**📚 Help Guide**

**📤 Upload:**
• Send any file directly
• Or use /upload command
• Max size: 4GB

**📥 Download:**
• Use /list to see files
• Copy file ID
• Use /download <file_id>

**🎥 Stream:**
• Use /list to see files
• Use /stream <file_id>
• Opens in MX Player/VLC

**🔧 Commands:**
/test - Check Wasabi connection
/list - Show all files
/upload - Upload file

**⚠️ Notes:**
• Stream links expire in 1 hour
• Files stored securely on Wasabi
"""
    await message.reply_text(help_text, reply_markup=get_main_keyboard())

@app.on_message(filters.command("upload"))
async def upload_command(client: Client, message: Message):
    """Handle /upload command"""
    await message.reply_text(
        "📤 **Send me your file!**\n\n"
        "Supported: Any file type\n"
        f"Max size: 4GB\n\n"
        "Just send the file and I'll upload it to Wasabi cloud."
    )

@app.on_message(filters.command("list"))
async def list_files_command(client: Client, message: Message):
    """Handle /list command"""
    status_msg = await message.reply_text("📋 **Fetching your files...**")
    
    files = wasabi.list_files()  # Remove await - now sync
    
    if not files:
        await status_msg.edit_text("❌ **No files found!**\n\nUpload a file using /upload")
        return
    
    # Store file mappings
    for file in files:
        file_id = hashlib.md5(file['key'].encode()).hexdigest()[:16]
        user_files[file_id] = file['key']
    
    # Create response
    text = "**📁 Your Files:**\n\n"
    for i, file in enumerate(files[:10], 1):
        file_name = os.path.basename(file['key'])
        file_id = hashlib.md5(file['key'].encode()).hexdigest()[:16]
        text += f"{i}. **{file_name}**\n"
        text += f"   📦 Size: `{format_file_size(file['size'])}`\n"
        text += f"   🆔 ID: `{file_id}`\n\n"
    
    if len(files) > 10:
        text += f"_... and {len(files) - 10} more files_"
    
    await status_msg.edit_text(text)
    
    # Show quick access buttons for first 5 files
    buttons = []
    for file in files[:5]:
        file_name = os.path.basename(file['key'])
        file_id = hashlib.md5(file['key'].encode()).hexdigest()[:16]
        buttons.append([InlineKeyboardButton(
            f"📄 {file_name[:30]}",
            callback_data=f"file_{file_id}"
        )])
    
    buttons.append([InlineKeyboardButton("🔄 Refresh", callback_data="refresh")])
    
    await client.send_message(
        message.chat.id,
        "**Quick Access:**\nTap a file for options:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

@app.on_message(filters.command("download"))
async def download_command(client: Client, message: Message):
    """Handle /download command"""
    parts = message.text.split(maxsplit=1)
    
    if len(parts) < 2:
        await message.reply_text(
            "❌ **Usage:** `/download <file_id>`\n\n"
            "Get file IDs from /list command"
        )
        return
    
    file_id = parts[1].strip()
    
    if file_id not in user_files:
        await message.reply_text("❌ **Invalid file ID!**\n\nUse /list to get valid IDs.")
        return
    
    file_key = user_files[file_id]
    file_name = os.path.basename(file_key)
    
    # Generate download link
    download_url = wasabi.get_direct_download_url(file_key, file_name)  # Remove await
    
    if download_url:
        file_size = wasabi.get_file_size(file_key)
        
        await message.reply_text(
            f"✅ **Download Ready!**\n\n"
            f"📁 **File:** `{file_name}`\n"
            f"📦 **Size:** `{format_file_size(file_size)}`\n\n"
            f"🔗 **Download Link:**\n`{download_url}`\n\n"
            f"⚠️ Link expires in 1 hour\n"
            f"🎥 For streaming: `/stream {file_id}`"
        )
    else:
        await message.reply_text("❌ **Failed to generate download link!**")

@app.on_message(filters.command("stream"))
async def stream_command(client: Client, message: Message):
    """Handle /stream command"""
    parts = message.text.split(maxsplit=1)
    
    if len(parts) < 2:
        await message.reply_text("❌ **Usage:** `/stream <file_id>`")
        return
    
    file_id = parts[1].strip()
    
    if file_id not in user_files:
        await message.reply_text("❌ **Invalid file ID!**")
        return
    
    file_key = user_files[file_id]
    file_name = os.path.basename(file_key)
    file_type = get_file_type(file_name)
    
    if file_type not in ["video", "audio"]:
        await message.reply_text("❌ **This file type cannot be streamed!**\n\nOnly video/audio files are supported.")
        return
    
    stream_url = wasabi.generate_presigned_url(file_key)  # Remove await
    
    if stream_url:
        await message.reply_text(
            f"🎬 **Stream Ready!**\n\n"
            f"📁 **File:** `{file_name}`\n\n"
            f"🔗 **Stream Link:**\n`{stream_url}`\n\n"
            f"**📱 How to stream:**\n"
            f"1. Copy the link above\n"
            f"2. Open MX Player or VLC\n"
            f"3. Tap 'Open Network Stream'\n"
            f"4. Paste the link\n\n"
            f"⚠️ Link expires in 1 hour"
        )
    else:
        await message.reply_text("❌ **Failed to generate stream link!**")

@app.on_message(filters.command("test"))
async def test_command(client: Client, message: Message):
    """Test Wasabi connection"""
    test_msg = await message.reply_text("🔄 **Testing Wasabi connection...**")
    
    if wasabi.test_connection():  # Remove await
        await test_msg.edit_text(
            "✅ **Wasabi Connected!**\n\n"
            f"📦 Bucket: `{Config.WASABI_BUCKET}`\n"
            f"🌍 Region: `{Config.WASABI_REGION}`\n\n"
            "Ready to store files!"
        )
    else:
        await test_msg.edit_text(
            "❌ **Connection Failed!**\n\n"
            "Please check:\n"
            "• Access Key\n"
            "• Secret Key\n"
            "• Bucket name\n"
            "• Region"
        )

@app.on_message(filters.document | filters.video | filters.audio)
async def handle_file_upload(client: Client, message: Message):
    """Handle file uploads"""
    
    # Get file info
    if message.document:
        file = message.document
        file_name = file.file_name
        file_size = file.file_size
    elif message.video:
        file = message.video
        file_name = f"{file.file_name or 'video'}.mp4"
        file_size = file.file_size
    elif message.audio:
        file = message.audio
        file_name = f"{file.file_name or 'audio'}.mp3"
        file_size = file.file_size
    else:
        await message.reply_text("❌ Unsupported file type!")
        return
    
    # Check file size
    if file_size > Config.MAX_FILE_SIZE:
        await message.reply_text(
            f"❌ **File too large!**\n\n"
            f"Max: 4GB\n"
            f"Your file: {format_file_size(file_size)}"
        )
        return
    
    # Start upload process
    status_msg = await message.reply_text(f"📥 **Downloading: {file_name}**\n\n0%")
    
    # Download file
    download_path = await client.download_media(
        message,
        file_name=f"{message.from_user.id}_{datetime.now().timestamp()}_{file_name}"
    )
    
    if not download_path:
        await status_msg.edit_text("❌ **Download failed!**")
        return
    
    await status_msg.edit_text(f"📤 **Uploading to Wasabi: {file_name}**\n\n0%")
    
    # Generate unique file key
    file_key = f"users/{message.from_user.id}/{datetime.now().strftime('%Y%m%d_%H%M%S')}_{file_name}"
    
    # Upload to Wasabi (sync)
    result = wasabi.upload_file(download_path, file_key)
    
    # Clean up
    if os.path.exists(download_path):
        os.remove(download_path)
    
    if result["success"]:
        file_id = hashlib.md5(file_key.encode()).hexdigest()[:16]
        user_files[file_id] = file_key
        
        await status_msg.edit_text(
            f"✅ **Upload Complete!**\n\n"
            f"📁 **File:** `{file_name}`\n"
            f"📦 **Size:** `{format_file_size(file_size)}`\n"
            f"🆔 **File ID:** `{file_id}`\n\n"
            f"**Next steps:**\n"
            f"• Download: `/download {file_id}`\n"
            f"• Stream: `/stream {file_id}`\n"
            f"• List all: `/list`",
            reply_markup=get_file_keyboard(file_id, get_file_type(file_name))
        )
    else:
        await status_msg.edit_text(f"❌ **Upload Failed!**\n\nError: {result.get('error', 'Unknown error')}")

@app.on_callback_query()
async def handle_callbacks(client: Client, callback_query: CallbackQuery):
    """Handle button callbacks"""
    data = callback_query.data
    
    if data == "upload":
        await upload_command(client, callback_query.message)
    
    elif data == "list":
        await list_files_command(client, callback_query.message)
    
    elif data == "download_help":
        await callback_query.message.reply_text(
            "📥 **How to download:**\n\n"
            "1. Use /list to see all files\n"
            "2. Copy the file ID\n"
            "3. Use /download <file_id>\n\n"
            "Example: `/download a1b2c3d4e5f6g7h8`"
        )
    
    elif data == "stream_help":
        await callback_query.message.reply_text(
            "🎥 **How to stream:**\n\n"
            "1. Use /list to see files\n"
            "2. Copy file ID\n"
            "3. Use /stream <file_id>\n"
            "4. Open link in MX Player/VLC\n\n"
            "⚠️ Only video/audio files supported"
        )
    
    elif data == "test":
        await test_command(client, callback_query.message)
    
    elif data == "help":
        await help_command(client, callback_query.message)
    
    elif data.startswith("file_"):
        file_id = data[5:]
        if file_id in user_files:
            file_key = user_files[file_id]
            file_name = os.path.basename(file_key)
            file_type = get_file_type(file_name)
            
            await callback_query.message.reply_text(
                f"**📁 {file_name}**\n\n"
                f"🆔 ID: `{file_id}`\n\n"
                f"Choose an action:",
                reply_markup=get_file_keyboard(file_id, file_type)
            )
    
    elif data.startswith("download_"):
        file_id = data[9:]
        if file_id in user_files:
            file_key = user_files[file_id]
            file_name = os.path.basename(file_key)
            
            download_url = wasabi.get_direct_download_url(file_key, file_name)
            
            if download_url:
                await callback_query.message.reply_text(
                    f"✅ **Download Link for {file_name}:**\n\n"
                    f"`{download_url}`"
                )
            else:
                await callback_query.message.reply_text("❌ Failed to generate link!")
    
    elif data.startswith("stream_"):
        file_id = data[7:]
        if file_id in user_files:
            file_key = user_files[file_id]
            file_name = os.path.basename(file_key)
            
            stream_url = wasabi.generate_presigned_url(file_key)
            
            if stream_url:
                await callback_query.message.reply_text(
                    f"🎬 **Stream Link for {file_name}:**\n\n"
                    f"`{stream_url}`"
                )
            else:
                await callback_query.message.reply_text("❌ Failed to generate stream link!")
    
    elif data == "refresh":
        await list_files_command(client, callback_query.message)
    
    elif data == "back":
        await callback_query.message.reply_text(
            "**Main Menu:**",
            reply_markup=get_main_keyboard()
        )
    
    await callback_query.answer()

if __name__ == "__main__":
    print("🚀 Starting Telegram File Bot with Wasabi Cloud Storage...")
    print(f"📦 Bucket: {Config.WASABI_BUCKET}")
    print(f"🌍 Region: {Config.WASABI_REGION}")
    print("✅ Bot is running!")
    app.run()
