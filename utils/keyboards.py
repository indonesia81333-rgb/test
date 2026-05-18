from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def get_main_keyboard():
    """Main menu keyboard"""
    keyboard = [
        [
            InlineKeyboardButton("📤 Upload", callback_data="upload"),
            InlineKeyboardButton("📁 List Files", callback_data="list")
        ],
        [
            InlineKeyboardButton("📥 Download", callback_data="download_help"),
            InlineKeyboardButton("🎥 Stream", callback_data="stream_help")
        ],
        [
            InlineKeyboardButton("🔧 Test", callback_data="test"),
            InlineKeyboardButton("❓ Help", callback_data="help")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_file_keyboard(file_id: str, file_type: str):
    """File-specific keyboard"""
    buttons = [
        [InlineKeyboardButton("📥 Download", callback_data=f"download_{file_id}")]
    ]
    
    if file_type in ["video", "audio"]:
        buttons.append([InlineKeyboardButton("🎬 Stream", callback_data=f"stream_{file_id}")])
    
    buttons.append([InlineKeyboardButton("🔙 Back", callback_data="back")])
    
    return InlineKeyboardMarkup(buttons)
