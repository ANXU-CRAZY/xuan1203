"""Alibaba Cloud OSS adapter for private contribution images."""
import re
from contextlib import closing
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import alibabacloud_oss_v2 as oss
from alibabacloud_oss_v2 import exceptions
from alibabacloud_oss_v2.signer import SignerV4
from alibabacloud_oss_v2.types import HttpRequest, SigningContext
from django.conf import settings
from requests.exceptions import RequestException

from .contribution_storage import CHUNK_BYTES, InvalidUpload, ObjectStorage, StorageUnavailable


def credentials_provider():
    role_name = settings.CONTRIBUTION_OSS_RAM_ROLE
    if not role_name:
        return oss.credentials.EnvironmentVariableCredentialsProvider()

    from alibabacloud_credentials.client import Client
    from alibabacloud_credentials.models import Config

    client = Client(Config(type='ecs_ram_role', role_name=role_name, disable_imds_v1=True))

    def fetch():
        try:
            credentials = client.get_credential()
        except Exception:
            # The credential SDK can raise transport, metadata, or configuration errors.
            raise StorageUnavailable from None
        if not credentials or not credentials.access_key_id or not credentials.access_key_secret:
            raise StorageUnavailable
        return oss.credentials.Credentials(credentials.access_key_id, credentials.access_key_secret,
                                           credentials.security_token)

    return oss.credentials.CredentialsProviderFunc(func=fetch)


class OSSStorage(ObjectStorage):
    provider = 'oss'

    def __init__(self):
        super().__init__(settings.CONTRIBUTION_OSS_BUCKET, settings.CONTRIBUTION_OSS_REGION)
        if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)+', self.region):
            raise StorageUnavailable
        self.public_domain = settings.CONTRIBUTION_OSS_PUBLIC_DOMAIN
        if self.public_domain and not re.fullmatch(r'[a-z0-9-]+(?:\.[a-z0-9-]+)+', self.public_domain):
            raise StorageUnavailable
        try:
            self.credentials = credentials_provider()
            config = dict(
                region=self.region, signature_version='v4', credentials_provider=self.credentials,
                connect_timeout=4, readwrite_timeout=15, retry_max_attempts=2,
            )
            self.public_client = oss.Client(oss.Config(
                **config, endpoint=f'https://{self.public_domain}' if self.public_domain else None,
                use_cname=bool(self.public_domain),
            ))
            self.client = self.public_client
            if settings.CONTRIBUTION_OSS_USE_INTERNAL_ENDPOINT:
                self.client = oss.Client(oss.Config(**config, use_internal_endpoint=True))
        except exceptions.BaseError:
            raise StorageUnavailable from None

    def sign_upload(self, media):
        if self.public_domain and media.bucket_name != self.bucket:
            raise StorageUnavailable
        headers = {
            'Content-Type': media.mime_type, 'Content-Length': str(media.file_size),
            'x-oss-meta-sha256': media.sha256,
        }
        key = quote(media.upload_key, safe='/')
        host = self.public_domain or f'{media.bucket_name}.oss-{self.region}.aliyuncs.com'
        url = f'https://{host}/{key}'
        request = HttpRequest('PUT', url, headers)
        try:
            # The SDK's Client.presign does not pass additional_headers to its V4 signer.
            context = SigningContext(
                product='oss', region=self.region, bucket=media.bucket_name, key=media.upload_key,
                request=request, credentials=self.credentials.get_credentials(),
                additional_headers={'content-length'},
            )
            context.auth_method_query = True
            context.expiration_time = datetime.now(timezone.utc) + timedelta(seconds=self.upload_ttl)
            SignerV4().sign(context)
        except exceptions.BaseError:
            raise StorageUnavailable from None
        return request.url, headers

    def sign_download(self, media):
        if self.public_domain and media.bucket_name != self.bucket:
            raise StorageUnavailable
        try:
            result = self.public_client.presign(oss.GetObjectRequest(
                bucket=media.bucket_name, key=media.object_key, response_cache_control='private, no-store',
            ), expires=timedelta(seconds=self.download_ttl))
        except exceptions.BaseError:
            raise StorageUnavailable from None
        return result.url

    def verify_and_publish(self, media):
        source = dict(bucket=media.bucket_name, key=media.upload_key)
        try:
            metadata = self.client.head_object(oss.HeadObjectRequest(**source))
            if metadata.content_length != media.file_size or metadata.content_type != media.mime_type:
                raise InvalidUpload('图片大小或 Content-Type 与申报不一致。')
            if metadata.content_encoding not in (None, '', 'identity'):
                raise InvalidUpload('图片必须以原始文件字节上传。')
            if not metadata.version_id or metadata.version_id == 'null':
                raise StorageUnavailable
            response = self.client.get_object(oss.GetObjectRequest(
                **source, version_id=metadata.version_id, if_match=metadata.etag,
            ))
            with closing(response.body) as body:
                dimensions = self.validate_image(body.iter_bytes(block_size=CHUNK_BYTES), media)
            self.client.copy_object(oss.CopyObjectRequest(
                bucket=media.bucket_name, key=media.object_key,
                source_bucket=media.bucket_name, source_key=media.upload_key,
                source_version_id=metadata.version_id, if_match=metadata.etag,
                metadata_directive='REPLACE', content_type=media.mime_type, cache_control='private, no-store',
            ))
            return dimensions
        except exceptions.BaseError as exc:
            while isinstance(exc, exceptions.OperationError):
                exc = exc.unwrap()
            if isinstance(exc, exceptions.ServiceError) and exc.status_code in (404, 412):
                raise InvalidUpload('图片尚未上传，或上传期间已变化，请重试。') from None
            raise StorageUnavailable from None
        except RequestException:
            raise StorageUnavailable from None
