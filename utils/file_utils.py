import os
from typing import Tuple

def get_file_type(file_path: str) -> str:
    """Determine file type based on extension"""
    ext = os.path.splitext(file_path)[1].lower()
    
    video_extensions = ['.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.webm', '.m4v']
    audio_extensions = ['.mp3', '.wav', '.flac', '.m4a', '.aac', '.ogg']
    image_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp']
    document_extensions = ['.pdf', '.doc', '.docx', '.txt', '.xls', '.xlsx', '.zip', '.rar']
    
    if ext in video_extensions:
        return "video"
    elif ext in audio_extensions:
        return "audio"
    elif ext in image_extensions:
        return "image"
    elif ext in document_extensions:
        return "document"
    else:
        return "other"

def format_file_size(size_bytes: int) -> str:
    """Format file size in human-readable format"""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} PB"

def is_streamable(file_type: str) -> bool:
    """Check if file type is streamable"""
    return file_type in ["video", "audio"]

def get_mime_type(file_path: str) -> str:
    """Get MIME type of file"""
    ext = os.path.splitext(file_path)[1].lower()
    mime_types = {
        '.mp4': 'video/mp4',
        '.mkv': 'video/x-matroska',
        '.mp3': 'audio/mpeg',
        '.pdf': 'application/pdf',
        '.jpg': 'image/jpeg',
        '.png': 'image/png'
    }
    return mime_types.get(ext, 'application/octet-stream')
