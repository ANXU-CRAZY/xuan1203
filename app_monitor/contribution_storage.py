"""Private S3 storage for directly uploaded contribution images."""
import base64
import hashlib
import tempfile
from contextlib import closing

from django.conf import settings
from PIL import Image
from PIL.Image import open as open_image


IMAGE_FORMATS = {
    'image/jpeg': ('JPEG', ('.jpg', '.jpeg')),
    'image/png': ('PNG', ('.png',)),
    'image/webp': ('WEBP', ('.webp',)),
}


class StorageUnavailable(Exception):
    pass


class InvalidUpload(Exception):
    pass


class StorageService:
    provider = 's3'

    def __init__(self):
        self.bucket = settings.CONTRIBUTION_STORAGE_BUCKET
        self.upload_ttl = settings.CONTRIBUTION_UPLOAD_TTL
        self.download_ttl = settings.CONTRIBUTION_DOWNLOAD_TTL
        if (not self.bucket or not settings.CONTRIBUTION_STORAGE_REGION
                or not 300 <= self.upload_ttl <= 900 or not 60 <= self.download_ttl <= 900):
            raise StorageUnavailable
        from boto3 import client
        from botocore.config import Config
        from botocore.exceptions import BotoCoreError, ClientError

        self.errors = (BotoCoreError, ClientError)
        self.client_error = ClientError
        try:
            self.client = client('s3', region_name=settings.CONTRIBUTION_STORAGE_REGION, config=Config(
                signature_version='s3v4', connect_timeout=4, read_timeout=15,
                retries={'total_max_attempts': 2},
            ))
        except self.errors:
            raise StorageUnavailable from None

    def sign_upload(self, media):
        checksum = base64.b64encode(bytes.fromhex(media.sha256)).decode('ascii')
        params = {
            'Bucket': media.bucket_name, 'Key': media.upload_key, 'ContentLength': media.file_size,
            'ContentType': media.mime_type, 'ChecksumSHA256': checksum,
        }
        try:
            url = self.client.generate_presigned_url('put_object', Params=params, ExpiresIn=self.upload_ttl)
        except self.errors:
            raise StorageUnavailable from None
        return url, {
            'Content-Type': media.mime_type, 'Content-Length': str(media.file_size),
            'x-amz-checksum-sha256': checksum,
        }

    def sign_download(self, media):
        try:
            return self.client.generate_presigned_url('get_object', Params={
                'Bucket': media.bucket_name, 'Key': media.object_key,
                'ResponseCacheControl': 'private, no-store',
            }, ExpiresIn=self.download_ttl)
        except self.errors:
            raise StorageUnavailable from None

    def verify_and_publish(self, media):
        """Check staged bytes and copy the verified object within S3 to a server-only key."""
        source = {'Bucket': media.bucket_name, 'Key': media.upload_key}
        try:
            metadata = self.client.head_object(**source)
            if (metadata['ContentLength'] != media.file_size or
                    metadata.get('ContentType') != media.mime_type):
                raise InvalidUpload('图片大小或 Content-Type 与申报不一致。')
            etag = metadata['ETag']
            response = self.client.get_object(**source, IfMatch=etag)
            with closing(response['Body']) as body:
                dimensions = self._validate_image(body, media)
            self.client.copy_object(
                Bucket=media.bucket_name, Key=media.object_key, CopySource=source,
                CopySourceIfMatch=etag, MetadataDirective='REPLACE', ContentType=media.mime_type,
                CacheControl='private, no-store',
            )
            return dimensions
        except self.client_error as exc:
            if exc.response['ResponseMetadata'].get('HTTPStatusCode') in (404, 412):
                raise InvalidUpload('图片尚未上传，或上传期间已变化，请重试。') from None
            raise StorageUnavailable from None
        except self.errors:
            raise StorageUnavailable from None

    @staticmethod
    def _validate_image(body, media):
        size = 0
        checksum = hashlib.sha256()
        with tempfile.SpooledTemporaryFile(max_size=1024 * 1024) as data:
            for chunk in body.iter_chunks(chunk_size=256 * 1024):
                size += len(chunk)
                if size > media.file_size:
                    raise InvalidUpload('图片超过申报大小。')
                checksum.update(chunk)
                data.write(chunk)
            if size != media.file_size or checksum.hexdigest() != media.sha256:
                raise InvalidUpload('图片大小或 SHA-256 校验失败。')
            data.seek(0)
            expected_format = IMAGE_FORMATS[media.mime_type][0]
            try:
                with open_image(data, formats=[expected_format]) as image:
                    width, height = image.size
                    if (width * height > settings.CONTRIBUTION_MAX_IMAGE_PIXELS or
                            getattr(image, 'n_frames', 1) != 1):
                        raise InvalidUpload('图片像素过多或为动图。')
                    image.verify()
                data.seek(0)
                with open_image(data, formats=[expected_format]) as image:
                    image.load()
            except (OSError, SyntaxError, ValueError, Image.DecompressionBombError):
                raise InvalidUpload('图片内容损坏或实际格式与申报不符。') from None
        return width, height
