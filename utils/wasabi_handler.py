import boto3
from botocore.config import Config as BotoConfig
from botocore.exceptions import ClientError
import os
import asyncio
from typing import Optional, Dict, Any
from concurrent.futures import ThreadPoolExecutor
from config import Config

class WasabiHandler:
    def __init__(self):
        self.bucket = Config.WASABI_BUCKET
        self.session = boto3.session.Session()
        self.executor = ThreadPoolExecutor(max_workers=5)
        
        self.client = self.session.client(
            's3',
            region_name=Config.WASABI_REGION,
            endpoint_url=Config.WASABI_ENDPOINT,
            aws_access_key_id=Config.WASABI_ACCESS_KEY,
            aws_secret_access_key=Config.WASABI_SECRET_KEY,
            config=BotoConfig(signature_version='s3v4')
        )
    
    async def upload_file(self, file_path: str, file_key: str, progress_callback=None) -> Dict[str, Any]:
        """Upload file to Wasabi with progress tracking"""
        try:
            file_size = os.path.getsize(file_path)
            uploaded_bytes = 0
            
            def upload():
                nonlocal uploaded_bytes
                with open(file_path, 'rb') as f:
                    self.client.upload_fileobj(
                        f,
                        self.bucket,
                        file_key,
                        Callback=lambda bytes_transferred: self._update_progress(
                            bytes_transferred, file_size, progress_callback
                        )
                    )
                return file_key
            
            await asyncio.get_event_loop().run_in_executor(self.executor, upload)
            
            # Generate download URL
            url = self.generate_presigned_url(file_key)
            
            return {
                "success": True,
                "file_key": file_key,
                "url": url,
                "size": file_size
            }
            
        except ClientError as e:
            return {"success": False, "error": str(e)}
    
    def _update_progress(self, transferred: int, total: int, callback):
        """Update upload progress"""
        if callback:
            progress = (transferred / total) * 100
            callback(progress)
    
    async def download_file(self, file_key: str, download_path: str, progress_callback=None) -> Dict[str, Any]:
        """Download file from Wasabi with progress tracking"""
        try:
            def download():
                with open(download_path, 'wb') as f:
                    self.client.download_fileobj(
                        self.bucket,
                        file_key,
                        f,
                        Callback=lambda bytes_transferred: self._update_progress(
                            bytes_transferred, 
                            self.get_file_size(file_key), 
                            progress_callback
                        )
                    )
                return download_path
            
            await asyncio.get_event_loop().run_in_executor(self.executor, download)
            
            return {
                "success": True,
                "path": download_path,
                "size": self.get_file_size(file_key)
            }
            
        except ClientError as e:
            return {"success": False, "error": str(e)}
    
    def get_file_size(self, file_key: str) -> int:
        """Get file size from Wasabi"""
        try:
            response = self.client.head_object(Bucket=self.bucket, Key=file_key)
            return response['ContentLength']
        except:
            return 0
    
    def generate_presigned_url(self, file_key: str, expiry: int = Config.STREAM_EXPIRY) -> str:
        """Generate presigned URL for streaming"""
        try:
            url = self.client.generate_presigned_url(
                'get_object',
                Params={'Bucket': self.bucket, 'Key': file_key},
                ExpiresIn=expiry
            )
            return url
        except:
            return None
    
    async def list_files(self) -> list:
        """List all files in bucket"""
        try:
            objects = []
            paginator = self.client.get_paginator('list_objects_v2')
            
            for page in paginator.paginate(Bucket=self.bucket):
                if 'Contents' in page:
                    for obj in page['Contents']:
                        objects.append({
                            'key': obj['Key'],
                            'size': obj['Size'],
                            'last_modified': obj['LastModified']
                        })
            return objects
        except:
            return []
    
    async def delete_file(self, file_key: str) -> bool:
        """Delete file from Wasabi"""
        try:
            self.client.delete_object(Bucket=self.bucket, Key=file_key)
            return True
        except:
            return False
    
    async def test_connection(self) -> bool:
        """Test Wasabi connection"""
        try:
            self.client.head_bucket(Bucket=self.bucket)
            return True
        except:
            return False
