import os

def get_file_type(file_path: str) -> str:
    """Determine file type"""
    ext = os.path.splitext(file_path)[1].lower()
    
    video_extensions = ['.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.webm', '.m4v']
    audio_extensions = ['.mp3', '.wav', '.flac', '.m4a', '.aac', '.ogg']
    image_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp']
    
    if ext in video_extensions:
        return "video"
    elif ext in audio_extensions:
        return "audio"
    elif ext in image_extensions:
        return "image"
    else:
        return "document"

def format_file_size(size_bytes: int) -> str:
    """Format file size"""
    if size_bytes == 0:
        return "0 B"
    
    size_names = ["B", "KB", "MB", "GB", "TB"]
    i = 0
    while size_bytes >= 1024 and i < len(size_names) - 1:
        size_bytes /= 1024.0
        i += 1
    
    return f"{size_bytes:.2f} {size_names[i]}"
