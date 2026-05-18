import boto3
from botocore.config import Config as BotoConfig
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
            
            # Run sync upload in executor
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                self.executor,
                self._sync_upload,
                file_path,
                file_key,
                file_size,
                progress_callback
            )
            
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
    
    def _sync_upload(self, file_path: str, file_key: str, file_size: int, progress_callback):
        """Synchronous upload method"""
        try:
            with open(file_path, 'rb') as f:
                self.client.upload_fileobj(
                    f,
                    self.bucket,
                    file_key,
                    Callback=lambda bytes_transferred: self._update_progress(
                        bytes_transferred, file_size, progress_callback
                    ) if progress_callback else None
                )
        except Exception as e:
            raise e
    
    def _update_progress(self, transferred: int, total: int, callback):
        """Update progress"""
        if callback:
            progress = (transferred / total) * 100
            callback(progress)
    
    async def download_file(self, file_key: str, download_path: str, progress_callback=None) -> Dict[str, Any]:
        """Download file from Wasabi"""
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                self.executor,
                self._sync_download,
                file_key,
                download_path,
                progress_callback
            )
            
            return {
                "success": True,
                "path": download_path,
                "size": self.get_file_size(file_key)
            }
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def _sync_download(self, file_key: str, download_path: str, progress_callback):
        """Synchronous download method"""
        try:
            file_size = self.get_file_size(file_key)
            with open(download_path, 'wb') as f:
                self.client.download_fileobj(
                    self.bucket,
                    file_key,
                    f,
                    Callback=lambda bytes_transferred: self._update_progress(
                        bytes_transferred, file_size, progress_callback
                    ) if progress_callback else None
                )
        except Exception as e:
            raise e
    
    def get_file_size(self, file_key: str) -> int:
        """Get file size"""
        try:
            response = self.client.head_object(Bucket=self.bucket, Key=file_key)
            return response['ContentLength']
        except:
            return 0
    
    async def generate_presigned_url(self, file_key: str, expiry: int = 3600) -> Optional[str]:
        """Generate presigned URL"""
        try:
            loop = asyncio.get_event_loop()
            url = await loop.run_in_executor(
                self.executor,
                self._sync_generate_url,
                file_key,
                expiry
            )
            return url
            
        except Exception as e:
            print(f"Error generating URL: {e}")
            return None
    
    def _sync_generate_url(self, file_key: str, expiry: int) -> Optional[str]:
        """Synchronous URL generation"""
        try:
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
        except Exception as e:
            print(f"Error: {e}")
            return None
    
    async def get_direct_download_url(self, file_key: str, filename: str = None) -> Optional[str]:
        """Generate direct download URL"""
        try:
            loop = asyncio.get_event_loop()
            url = await loop.run_in_executor(
                self.executor,
                self._sync_download_url,
                file_key,
                filename
            )
            return url
            
        except Exception as e:
            print(f"Error generating download URL: {e}")
            return None
    
    def _sync_download_url(self, file_key: str, filename: str) -> Optional[str]:
        """Synchronous download URL generation"""
        try:
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
        except Exception as e:
            print(f"Error: {e}")
            return None
    
    async def list_files(self) -> list:
        """List all files"""
        try:
            loop = asyncio.get_event_loop()
            files = await loop.run_in_executor(
                self.executor,
                self._sync_list_files
            )
            return files
        except Exception as e:
            print(f"Error listing files: {e}")
            return []
    
    def _sync_list_files(self) -> list:
        """Synchronous file listing"""
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
        except Exception as e:
            print(f"Error: {e}")
            return []
    
    async def delete_file(self, file_key: str) -> bool:
        """Delete file"""
        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                self.executor,
                self._sync_delete,
                file_key
            )
            return result
        except:
            return False
    
    def _sync_delete(self, file_key: str) -> bool:
        """Synchronous delete"""
        try:
            self.client.delete_object(Bucket=self.bucket, Key=file_key)
            return True
        except:
            return False
    
    async def test_connection(self) -> bool:
        """Test connection"""
        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                self.executor,
                self._sync_test
            )
            return result
        except Exception as e:
            print(f"Connection test failed: {e}")
            return False
    
    def _sync_test(self) -> bool:
        """Synchronous test"""
        try:
            self.client.head_bucket(Bucket=self.bucket)
            return True
        except:
            return False
