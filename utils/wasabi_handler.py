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
        
        # Configure Wasabi client
        self.client = self.session.client(
            's3',
            region_name=Config.WASABI_REGION,
            endpoint_url=f"https://s3.{Config.WASABI_REGION}.wasabisys.com",
            aws_access_key_id=Config.WASABI_ACCESS_KEY,
            aws_secret_access_key=Config.WASABI_SECRET_KEY,
            config=BotoConfig(
                signature_version='s3v4',
                s3={'addressing_style': 'virtual'}
            )
        )
    
    async def upload_file(self, file_path: str, file_key: str, progress_callback=None) -> Dict[str, Any]:
        """Upload file to Wasabi"""
        try:
            file_size = os.path.getsize(file_path)
            
            def upload():
                with open(file_path, 'rb') as f:
                    self.client.upload_fileobj(
                        f,
                        self.bucket,
                        file_key,
                        Callback=lambda bytes_transferred: self._update_progress(
                            bytes_transferred, file_size, progress_callback
                        ) if progress_callback else None
                    )
                return file_key
            
            await asyncio.get_event_loop().run_in_executor(self.executor, upload)
            
            # Generate download URL
            url = await self.generate_presigned_url(file_key)
            
            return {
                "success": True,
                "file_key": file_key,
                "url": url,
                "size": file_size
            }
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def _update_progress(self, transferred: int, total: int, callback):
        """Update progress"""
        if callback:
            progress = (transferred / total) * 100
            callback(progress)
    
    async def download_file(self, file_key: str, download_path: str, progress_callback=None) -> Dict[str, Any]:
        """Download file from Wasabi"""
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
                        ) if progress_callback else None
                    )
                return download_path
            
            await asyncio.get_event_loop().run_in_executor(self.executor, download)
            
            return {
                "success": True,
                "path": download_path,
                "size": self.get_file_size(file_key)
            }
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def get_file_size(self, file_key: str) -> int:
        """Get file size"""
        try:
            response = self.client.head_object(Bucket=self.bucket, Key=file_key)
            return response['ContentLength']
        except:
            return 0
    
    async def generate_presigned_url(self, file_key: str, expiry: int = 3600) -> Optional[str]:
        """Generate presigned URL for streaming"""
        try:
            def generate():
                url = self.client.generate_presigned_url(
                    'get_object',
                    Params={
                        'Bucket': self.bucket,
                        'Key': file_key,
                        'ResponseContentDisposition': 'inline'
                    },
                    ExpiresIn=expiry,
                    HttpMethod='GET'
                )
                return url
            
            url = await asyncio.get_event_loop().run_in_executor(self.executor, generate)
            return url
            
        except Exception as e:
            print(f"Error generating URL: {e}")
            return None
    
    async def get_direct_download_url(self, file_key: str, filename: str = None) -> Optional[str]:
        """Generate direct download URL"""
        try:
            def generate():
                params = {
                    'Bucket': self.bucket,
                    'Key': file_key
                }
                
                if filename:
                    params['ResponseContentDisposition'] = f'attachment; filename="{filename}"'
                else:
                    params['ResponseContentDisposition'] = 'attachment'
                
                url = self.client.generate_presigned_url(
                    'get_object',
                    Params=params,
                    ExpiresIn=3600,
                    HttpMethod='GET'
                )
                return url
            
            url = await asyncio.get_event_loop().run_in_executor(self.executor, generate)
            return url
            
        except Exception as e:
            print(f"Error generating download URL: {e}")
            return None
    
    async def list_files(self) -> list:
        """List all files"""
        try:
            objects = []
            paginator = self.client.get_paginator('list_objects_v2')
            
            def fetch():
                for page in paginator.paginate(Bucket=self.bucket):
                    if 'Contents' in page:
                        for obj in page['Contents']:
                            objects.append({
                                'key': obj['Key'],
                                'size': obj['Size'],
                                'last_modified': obj['LastModified']
                            })
                return objects
            
            return await asyncio.get_event_loop().run_in_executor(self.executor, fetch)
        except Exception as e:
            print(f"Error listing files: {e}")
            return []
    
    async def delete_file(self, file_key: str) -> bool:
        """Delete file"""
        try:
            def delete():
                self.client.delete_object(Bucket=self.bucket, Key=file_key)
                return True
            
            return await asyncio.get_event_loop().run_in_executor(self.executor, delete)
        except:
            return False
    
    async def test_connection(self) -> bool:
        """Test connection"""
        try:
            def test():
                self.client.head_bucket(Bucket=self.bucket)
                return True
            
            return await asyncio.get_event_loop().run_in_executor(self.executor, test)
        except Exception as e:
            print(f"Connection test failed: {e}")
            return False
