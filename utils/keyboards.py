from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def get_main_keyboard():
    """Get main menu keyboard"""
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
            InlineKeyboardButton("ℹ️ Help", callback_data="help"),
            InlineKeyboardButton("🔧 Test", callback_data="test")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_file_keyboard(file_id, file_type):
    """Get file-specific action keyboard"""
    buttons = [
        [InlineKeyboardButton("📥 Download", callback_data=f"download_{file_id}")]
    ]
    
    if file_type in ["video", "audio"]:
        buttons.append([InlineKeyboardButton("🎬 Stream to MX Player/VLC", callback_data=f"stream_{file_id}")])
        buttons.append([InlineKeyboardButton("🌐 Open in Web Player", callback_data=f"web_{file_id}")])
    
    buttons.append([InlineKeyboardButton("🔙 Back to Files", callback_data="refresh_list")])
    
    return InlineKeyboardMarkup(buttons)
