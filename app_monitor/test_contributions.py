import hashlib
import io
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from urllib.parse import parse_qs, urlparse
from unittest.mock import Mock, patch
from uuid import uuid4

import alibabacloud_oss_v2 as oss
import boto3
from botocore.config import Config
from botocore.response import StreamingBody
from botocore.stub import Stubber
from django.contrib.auth import get_user_model
from django.db import connections
from django.test import SimpleTestCase, TestCase, TransactionTestCase, override_settings
from PIL import Image
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from .contribution_oss import OSSStorage
from .contribution_points import rank_for
from .contribution_storage import InvalidUpload, StorageService, StorageUnavailable, storage_for_provider
from .models import ObservationMedia, ObservationRecord, PointTransaction, Product, SpeciesInfo, WetlandZone


START = '/api/observations/upload-session/'
PROFILE = '/api/users/me/contribution-profile/'


def upload_data(*kinds):
    group = str(uuid4())
    return {
        'clientObservationId': str(uuid4()), 'title': '湿地观测',
        'capturedAt': '2026-11-22T10:30:00+08:00',
        'location': {'longitude': 113.6, 'latitude': 34.9, 'accuracy': 8.5, 'source': 'gps'},
        'device': {'phoneModel': 'Test Android', 'thermalDeviceModel': 'E20 Plus'},
        'media': [
            dict(clientMediaId=str(uuid4()), type=kind, pairGroupId=group,
                 filename=kind + '.jpg', mimeType='image/jpeg', fileSize=100, sha256='a' * 64)
            for kind in kinds
        ],
    }


class ContributionApiTests(TestCase):
    def setUp(self):
        self.owner = get_user_model().objects.create_user(username='contributor')
        self.other = get_user_model().objects.create_user(username='another-user')
        token = Token.objects.create(user=self.owner)
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')
        patcher = patch('app_monitor.contributions.storage_for_provider')
        self.get_storage = patcher.start()
        self.addCleanup(patcher.stop)
        self.storage = self.get_storage.return_value
        self.storage.provider, self.storage.bucket = 's3', 'test-private-bucket'
        self.storage.upload_ttl = 600
        self.storage.sign_upload.side_effect = lambda media: ('https://example.invalid/put/' + media.upload_key, {})
        self.storage.verify_and_publish.return_value = (16, 20)
        self.storage.sign_download.side_effect = lambda media: 'https://example.invalid/get/' + media.object_key

    def start(self, data):
        response = self.client.post(START, data, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        body = response.json()
        uploads = [
            dict(clientMediaId=item['clientMediaId'], objectKey=item['objectKey'], sha256='a' * 64)
            for item in body['uploads']
        ]
        return body['observationId'], {'media': uploads}

    def complete(self, pk, manifest):
        return self.client.post(f'/api/observations/{pk}/complete/', manifest, format='json')

    def test_paired_upload_retry_completion_and_soft_delete(self):
        self.owner.profile.total_contribution_points = 1175
        self.owner.profile.save(update_fields=['total_contribution_points'])
        payload = upload_data('rgb', 'thermal')
        pk, manifest = self.start(payload)
        retry = self.client.post(START, payload, format='json')
        self.assertEqual(retry.status_code, 200)
        self.assertEqual(retry.json()['observationId'], pk)
        self.assertEqual(ObservationRecord.objects.count(), 1)
        self.assertEqual(ObservationMedia.objects.filter(
            observation_id=pk, pair_group_id=payload['media'][0]['pairGroupId'],
        ).count(), 2)
        self.assertEqual(self.client.get(f'/api/observations/{pk}/upload-status/').json()['status'], 'uploading')

        result = self.complete(pk, manifest)
        self.assertEqual(result.status_code, 200, result.data)
        self.assertEqual(result.json()['pointsAwarded'], 25)
        self.assertEqual(result.json()['rank']['code'], 'ECO_GOLD_WING')
        self.assertEqual(self.complete(pk, manifest).json()['availablePoints'], 25)
        self.assertEqual(self.storage.verify_and_publish.call_count, 2)
        self.assertEqual(PointTransaction.objects.filter(observation_id=pk).count(), 1)
        self.assertEqual(self.client.post(START, payload, format='json').json()['uploads'], [])

        endpoint = f'/api/observations/{pk}/contribution/'
        response = self.client.get(endpoint)
        self.assertIn('private, no-store', response['Cache-Control'])
        self.assertTrue(response.json()['paired'])
        self.assertIn('contributions/images/', response.json()['rgbImageUrl'])
        with patch('app_monitor.contribution_api.storage_for_provider', return_value=self.storage):
            entries = self.client.get('/api/observations/mine/?status=completed&pageSize=1').json()
        self.assertEqual(entries['count'], 1)
        self.assertEqual(entries['results'][0]['observationId'], pk)
        self.assertEqual(self.client.delete(endpoint).status_code, 204)
        self.assertEqual(self.client.get(endpoint).status_code, 404)
        self.assertEqual(self.client.post(START, payload, format='json').status_code, 404)
        self.assertIsNotNone(ObservationRecord.objects.get(pk=pk).deleted_at)
        self.assertEqual(self.client.get(PROFILE).json()['totalContributionPoints'], 1200)

    def test_new_oss_capture_keeps_inflight_s3_capture_usable(self):
        existing = upload_data('rgb')
        pk, manifest = self.start(existing)
        oss_storage = Mock(provider='oss', bucket='example-private-bucket', upload_ttl=600)
        oss_storage.sign_upload.return_value = ('https://example.invalid/put', {})
        oss_storage.verify_and_publish.return_value = (16, 20)
        self.get_storage.side_effect = lambda provider=None: self.storage if provider == 's3' else oss_storage

        new_id, oss_manifest = self.start(upload_data('rgb', 'thermal'))
        providers = set(ObservationMedia.objects.filter(observation_id=new_id).values_list('storage_provider', flat=True))
        self.assertEqual(providers, {'oss'})
        self.storage.sign_upload.reset_mock()
        self.assertEqual(self.client.post(START, existing, format='json').status_code, 200)
        self.storage.sign_upload.assert_called_once()
        self.assertEqual(self.complete(new_id, oss_manifest).json()['pointsAwarded'], 25)
        self.assertEqual(self.complete(new_id, oss_manifest).json()['availablePoints'], 25)
        self.assertEqual(self.complete(pk, manifest).json()['pointsAwarded'], 15)
        self.assertEqual(PointTransaction.objects.count(), 2)

    def test_conflicts_and_partial_retry(self):
        payload = upload_data('rgb', 'thermal')
        pk, manifest = self.start(payload)
        self.assertEqual(self.client.post(START, {**payload, 'title': '不同观测'}, format='json').status_code, 409)
        bad = {'media': [{**item, 'objectKey': 'other-user/image.jpg'} for item in manifest['media']]}
        self.assertEqual(self.complete(pk, bad).status_code, 409)
        self.storage.verify_and_publish.assert_not_called()
        self.storage.verify_and_publish.side_effect = [(16, 20), InvalidUpload('图片尚未上传')]
        failed = self.complete(pk, manifest)
        self.assertEqual(failed.status_code, 409)
        self.assertEqual({item['status'] for item in failed.json()['media']}, {'verified', 'failed'})
        self.assertFalse(PointTransaction.objects.exists())
        self.assertEqual(len(self.client.post(START, payload, format='json').json()['uploads']), 1)
        self.storage.verify_and_publish.side_effect = None
        self.assertEqual(self.complete(pk, manifest).json()['pointsAwarded'], 25)
        self.assertEqual(self.storage.verify_and_publish.call_count, 3)

    def test_private_records_are_hidden_from_legacy_and_other_users(self):
        pk, manifest = self.start(upload_data('thermal'))
        self.assertEqual(self.complete(pk, manifest).status_code, 200)
        self.assertEqual(self.client.get(f'/api/observations/{pk}/').status_code, 404)
        anonymous = APIClient()
        self.assertEqual(anonymous.get(PROFILE).status_code, 401)
        stranger = APIClient()
        stranger.force_authenticate(self.other)
        for suffix in ('upload-status', 'contribution'):
            self.assertEqual(stranger.get(f'/api/observations/{pk}/{suffix}/').status_code, 404)
        self.assertEqual(stranger.delete(f'/api/observations/{pk}/contribution/').status_code, 404)
        self.assertEqual(stranger.post(f'/api/observations/{pk}/complete/', manifest, format='json').status_code, 404)
        self.assertEqual(stranger.get('/api/observations/mine/').json()['count'], 0)

    def test_validation_rejects_unpaired_unsafe_or_oversized_media(self):
        for field, value in (
            ('mimeType', 'image/svg+xml'), ('filename', '../rgb.jpg'), ('filename', 'rgb.png'),
            ('fileSize', 21 * 1024 * 1024), ('pairGroupId', str(uuid4())),
        ):
            data = upload_data('rgb', 'thermal')
            data['media'][0][field] = value
            self.assertEqual(self.client.post(START, data, format='json').status_code, 400, field)
        self.assertFalse(ObservationRecord.objects.exists())

    def test_redemption_and_game_points_cannot_change_contribution_rank(self):
        profile = self.owner.profile
        profile.score, profile.total_contribution_points = 1200, 1200
        profile.save()
        product = Product.objects.create(name='测试商品', price=1000, stock=2)
        endpoint = f'/api/products/{product.pk}/redeem/'
        for _ in range(2):
            result = self.client.post(endpoint, HTTP_IDEMPOTENCY_KEY='redeem-once')
            self.assertEqual(result.status_code, 200)
            self.assertEqual(result.json()['remaining_score'], 200)
        product.refresh_from_db()
        self.assertEqual(product.stock, 1)
        self.assertEqual(PointTransaction.objects.filter(transaction_type='redeem').count(), 1)
        self.assertEqual(self.client.patch('/api/profiles/me/', {'score': 99999}, format='json').json()['game_score'], 99999)
        result = self.client.get(PROFILE).json()
        self.assertEqual(result['availablePoints'], 200)
        self.assertEqual(result['totalContributionPoints'], 1200)
        self.assertEqual(result['rank']['code'], 'ECO_GOLD_WING')

    def test_legacy_web_create_still_uses_existing_format_and_balance(self):
        species = SpeciesInfo.objects.create(name_cn='测试鸟')
        zone = WetlandZone.objects.create(name='测试湿地')
        response = self.client.post('/api/observations/', {
            'species': species.pk, 'zone': zone.pk, 'observation_time': '2026-11-22', 'count': 1,
        }, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.json()['status'], 'pending')
        self.assertEqual(self.client.get(PROFILE).json()['availablePoints'], 10)


class ConcurrentConfirmationTests(TransactionTestCase):
    @patch('app_monitor.contributions.storage_for_provider')
    def test_two_verifiers_cannot_award_the_same_capture_twice(self, storage_class):
        owner = get_user_model().objects.create_user(username='concurrent')
        storage = storage_class.return_value
        storage.provider, storage.bucket = 's3', 'test-private-bucket'
        storage.upload_ttl = 600
        storage.sign_upload.return_value = 'https://example.invalid/put', {}
        barrier = Barrier(2, timeout=10)

        def verify(_media):
            barrier.wait()
            return 16, 20

        storage.verify_and_publish.side_effect = verify
        client = APIClient()
        client.force_authenticate(owner)
        session = client.post(START, upload_data('rgb'), format='json').json()
        upload = session['uploads'][0]
        manifest = {'media': [dict(clientMediaId=upload['clientMediaId'],
                                   objectKey=upload['objectKey'], sha256='a' * 64)]}
        endpoint = f"/api/observations/{session['observationId']}/complete/"

        def confirm():
            try:
                requester = APIClient()
                requester.force_authenticate(owner)
                result = requester.post(endpoint, manifest, format='json')
                return result.status_code, result.json()['availablePoints']
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            requests = list(pool.map(lambda _: confirm(), range(2)))
        self.assertEqual(requests, [(200, 15), (200, 15)])
        self.assertEqual(PointTransaction.objects.filter(user=owner).count(), 1)
        self.assertEqual(client.get(PROFILE).json()['completedObservationCount'], 1)


@override_settings(CONTRIBUTION_STORAGE_BUCKET='test-private-bucket', CONTRIBUTION_STORAGE_REGION='us-east-1')
class S3StorageTests(SimpleTestCase):
    def setUp(self):
        self.client_s3 = boto3.client('s3', region_name='us-east-1', aws_access_key_id='TESTKEY',
                                     aws_secret_access_key='test-not-a-real-secret', config=Config(signature_version='s3v4'))
        with patch('boto3.client', return_value=self.client_s3):
            self.storage = StorageService()
        data = io.BytesIO()
        Image.new('RGB', (16, 20)).save(data, format='JPEG')
        self.raw = data.getvalue()

    def media(self, data):
        return ObservationMedia(bucket_name=self.storage.bucket, upload_key='contributions/staging/1/rgb.jpg',
                                object_key='contributions/images/1/rgb.jpg', mime_type='image/jpeg',
                                file_size=len(data), sha256=hashlib.sha256(data).hexdigest())

    def test_signing_binds_content_type_length_and_sha256(self):
        media = self.media(self.raw)
        url, headers = self.storage.sign_upload(media)
        self.assertEqual(parse_qs(urlparse(url).query)['X-Amz-SignedHeaders'][0],
                         'content-length;content-type;host;x-amz-checksum-sha256')
        self.assertEqual(headers['Content-Length'], str(media.file_size))
        self.assertNotIn(media.object_key, url)

    def test_verify_then_conditional_cloud_copy(self):
        media = self.media(self.raw)
        source = {'Bucket': media.bucket_name, 'Key': media.upload_key}
        tag = '"opaque-etag"'
        with Stubber(self.client_s3) as stub:
            stub.add_response('head_object', {'ContentLength': media.file_size, 'ContentType': media.mime_type, 'ETag': tag}, source)
            stub.add_response('get_object', {'Body': StreamingBody(io.BytesIO(self.raw), media.file_size)}, {**source, 'IfMatch': tag})
            stub.add_response('copy_object', {}, dict(
                Bucket=media.bucket_name, Key=media.object_key, CopySource=source, CopySourceIfMatch=tag,
                MetadataDirective='REPLACE', ContentType=media.mime_type, CacheControl='private, no-store',
            ))
            self.assertEqual(self.storage.verify_and_publish(media), (16, 20))
            stub.assert_no_pending_responses()

    def test_matching_checksum_cannot_disguise_non_image(self):
        data = b'not a valid image'
        stream = StreamingBody(io.BytesIO(data), len(data))
        with self.assertRaises(InvalidUpload):
            self.storage.validate_image(stream.iter_chunks(), self.media(data))

    def test_rank_boundaries(self):
        self.assertEqual(rank_for(199)['name'], '湿地新芽')
        self.assertEqual(rank_for(200)['name'], '巡护青羽')
        self.assertEqual(rank_for(600)['name'], '碧水银羽')
        self.assertEqual(rank_for(1200)['name'], '生态金翼')
        self.assertEqual(rank_for(2500)['name'], '方舟守望者')


@override_settings(CONTRIBUTION_STORAGE_PROVIDER='oss', CONTRIBUTION_OSS_BUCKET='example-private-bucket',
                   CONTRIBUTION_OSS_REGION='cn-wulanchabu', CONTRIBUTION_OSS_RAM_ROLE='',
                   CONTRIBUTION_OSS_PUBLIC_DOMAIN='', CONTRIBUTION_OSS_USE_INTERNAL_ENDPOINT=False)
class OSSStorageTests(SimpleTestCase):
    def setUp(self):
        credentials = oss.credentials.StaticCredentialsProvider('example-id', 'example-secret', 'example-sts')
        with patch('app_monitor.contribution_oss.credentials_provider', return_value=credentials):
            self.storage = storage_for_provider()
        self.assertIsInstance(self.storage, OSSStorage)
        image = io.BytesIO()
        Image.new('RGB', (16, 20)).save(image, format='JPEG')
        self.raw = image.getvalue()
        self.media = ObservationMedia(
            bucket_name=self.storage.bucket, storage_provider='oss', upload_key='contributions/staging/1/rgb.jpg',
            object_key='contributions/images/1/rgb.jpg', mime_type='image/jpeg',
            file_size=len(self.raw), sha256=hashlib.sha256(self.raw).hexdigest(),
        )

    def test_sdk_upload_signature_uses_public_https_and_exact_headers(self):
        url, headers = self.storage.sign_upload(self.media)
        parsed = urlparse(url)
        self.assertEqual(parsed.scheme, 'https')
        self.assertEqual(parsed.hostname, 'example-private-bucket.oss-cn-wulanchabu.aliyuncs.com')
        self.assertEqual(parsed.path, '/' + self.media.upload_key)
        query = parse_qs(parsed.query)
        self.assertEqual(query['x-oss-signature-version'], ['OSS4-HMAC-SHA256'])
        self.assertEqual(query['x-oss-additional-headers'], ['content-length'])
        self.assertEqual(query['x-oss-security-token'], ['example-sts'])
        self.assertEqual(headers, {'Content-Length': str(self.media.file_size), 'Content-Type': 'image/jpeg',
                                   'x-oss-meta-sha256': self.media.sha256})
        download = urlparse(self.storage.sign_download(self.media))
        self.assertEqual(download.path, '/' + self.media.object_key)
        self.assertEqual(parse_qs(download.query)['response-cache-control'], ['private, no-store'])

    @override_settings(CONTRIBUTION_OSS_PUBLIC_DOMAIN='objects.example.com',
                       CONTRIBUTION_OSS_USE_INTERNAL_ENDPOINT=True)
    def test_oss_custom_public_domain_is_used_with_internal_server_client(self):
        with patch('app_monitor.contribution_oss.credentials_provider', return_value=self.storage.credentials):
            storage = storage_for_provider()
        upload, _ = storage.sign_upload(self.media)
        download = storage.sign_download(self.media)
        self.assertEqual(urlparse(upload).netloc, 'objects.example.com')
        self.assertEqual(urlparse(download).netloc, 'objects.example.com')
        self.assertEqual(urlparse(download).path, '/' + self.media.object_key)
        self.assertIsNot(storage.public_client, storage.client)

    def test_version_checked_and_copied_even_if_staging_key_is_reuploaded(self):
        client = Mock(spec=oss.Client)
        self.storage.client = client
        version, etag = 'verified-staging-version', '"verified-etag"'
        client.head_object.return_value = oss.HeadObjectResult(
            content_length=len(self.raw), content_type='image/jpeg', version_id=version, etag=etag,
        )
        body = Mock()
        body.iter_bytes.return_value = iter([self.raw])
        client.get_object.return_value = oss.GetObjectResult(body=body)
        self.assertEqual(self.storage.verify_and_publish(self.media), (16, 20))
        get = client.get_object.call_args.args[0]
        copy = client.copy_object.call_args.args[0]
        self.assertEqual((get.version_id, get.if_match), (version, etag))
        self.assertEqual((copy.source_version_id, copy.if_match), (version, etag))
        self.assertEqual((copy.source_key, copy.key), (self.media.upload_key, self.media.object_key))
        body.close.assert_called_once()

    def test_unversioned_images_are_never_published(self):
        client = Mock(spec=oss.Client)
        self.storage.client = client
        client.head_object.return_value = oss.HeadObjectResult(
            content_length=len(self.raw), content_type='image/jpeg', version_id='null',
        )
        with self.assertRaises(StorageUnavailable):
            self.storage.verify_and_publish(self.media)
        client.get_object.assert_not_called()
        client.copy_object.assert_not_called()

    def test_provider_errors_do_not_expose_credential_details(self):
        client = Mock(spec=oss.Client)
        self.storage.client = client
        for status_code, error in [(404, InvalidUpload), (412, InvalidUpload), (403, StorageUnavailable)]:
            with self.subTest(status_code=status_code):
                client.head_object.side_effect = oss.exceptions.OperationError(
                    name='HeadObject', error=oss.exceptions.ServiceError(
                        status_code=status_code, code='Test', message='sensitive details', request_id='test',
                        ec='', timestamp='', request_target='',
                    ),
                )
                with self.assertRaises(error) as context:
                    self.storage.verify_and_publish(self.media)
                self.assertNotIn('sensitive details', str(context.exception))
        client.copy_object.assert_not_called()
