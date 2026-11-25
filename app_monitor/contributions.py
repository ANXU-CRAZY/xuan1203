"""Persistence and upload lifecycle for private Android observations."""
import hashlib
import json
from datetime import timedelta

from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.http import Http404
from django.utils import timezone

from .contribution_points import award_observation, reward_for
from .contribution_storage import IMAGE_FORMATS, InvalidUpload, storage_for_provider
from .models import ObservationMedia, ObservationRecord, UserProfile


UploadStatus = ObservationRecord.UploadStatus
MediaStatus = ObservationMedia.Status


class ManifestConflict(Exception):
    pass


def owned_observations(user):
    return ObservationRecord.objects.filter(
        uploader=user, client_observation_id__isnull=False, deleted_at__isnull=True,
    )


def upload_session(user, data):
    # Keep device/capture metadata immutable for a given offline UUID.
    payload = json.dumps({**data, 'capturedAt': data['capturedAt'].isoformat()},
                         cls=DjangoJSONEncoder, sort_keys=True, ensure_ascii=False)
    fingerprint = hashlib.sha256(payload.encode('utf-8')).hexdigest()
    existing = ObservationRecord.objects.filter(
        uploader=user, client_observation_id=data['clientObservationId'],
    ).first()
    if existing and existing.deleted_at:
        raise Http404
    if existing and existing.upload_manifest_hash != fingerprint:
        raise ManifestConflict
    if existing and existing.upload_status == UploadStatus.COMPLETED:
        return existing, [], False

    with transaction.atomic():
        location, device = data['location'], data['device']
        now = timezone.now()
        observation, created = ObservationRecord.objects.select_for_update().get_or_create(
            uploader=user, client_observation_id=data['clientObservationId'],
            defaults=dict(
                title=data['title'], description=data['description'], submitted_species_name=data['speciesName'],
                captured_at=data['capturedAt'], observation_time=timezone.localdate(data['capturedAt']),
                longitude=location.get('longitude'), latitude=location.get('latitude'),
                location_accuracy=location.get('accuracy'), location_source=location.get('source', ''),
                device_model=device.get('phoneModel', ''), thermal_device_model=device.get('thermalDeviceModel', ''),
                upload_created_at=now, upload_updated_at=now, upload_status=UploadStatus.UPLOADING,
                upload_manifest_hash=fingerprint,
            ),
        )
        if observation.deleted_at:
            raise Http404
        if observation.upload_manifest_hash != fingerprint:
            raise ManifestConflict
        if created:
            storage = storage_for_provider()
            ObservationMedia.objects.bulk_create([_new_media(observation, item, storage) for item in data['media']])
        pending = list(observation.media.exclude(upload_status=MediaStatus.VERIFIED))
    if not pending:
        return observation, [], created
    if not created:
        storage = storage_for_provider(pending[0].storage_provider)
    uploads = []
    for media in pending:
        expires_at = timezone.now() + timedelta(seconds=storage.upload_ttl)
        url, headers = storage.sign_upload(media)
        uploads.append(dict(clientMediaId=media.client_media_id, objectKey=media.upload_key,
                            uploadUrl=url, method='PUT', headers=headers, expiresAt=expires_at))
    return observation, uploads, created


def _new_media(observation, data, storage):
    kind = data['type']
    suffix = IMAGE_FORMATS[data['mimeType']][1][0]
    path = f'{observation.uploader_id}/{observation.pk}/{data["clientMediaId"]}/{kind}{suffix}'
    return ObservationMedia(
        observation=observation, client_media_id=data['clientMediaId'], kind=kind,
        pair_group_id=data['pairGroupId'], storage_provider=storage.provider, bucket_name=storage.bucket,
        upload_key=f'contributions/staging/{path}', object_key=f'contributions/images/{path}',
        original_filename=data['filename'], mime_type=data['mimeType'], file_size=data['fileSize'], sha256=data['sha256'],
    )


def complete_observation(user, observation, submitted):
    media = list(observation.media.all())
    actual = {item.client_media_id: (item.upload_key, item.sha256) for item in media}
    claimed = {item['clientMediaId']: (item['objectKey'], item['sha256'].lower()) for item in submitted}
    if len(claimed) != len(submitted) or claimed != actual:
        raise ManifestConflict
    if not media or len({item.pair_group_id for item in media}) != 1:
        raise ManifestConflict
    if observation.upload_status == UploadStatus.COMPLETED:
        return observation, UserProfile.objects.get(user=user)

    # Validate the uploaded bytes before copying the verified object and awarding points.
    storage = storage_for_provider(media[0].storage_provider)
    verified, failures = {}, {}
    for item in media:
        if item.upload_status == MediaStatus.VERIFIED:
            continue
        try:
            verified[item.pk] = storage.verify_and_publish(item)
        except InvalidUpload as exc:
            failures[item.pk] = str(exc)

    with transaction.atomic():
        locked = owned_observations(user).select_for_update().filter(pk=observation.pk).first()
        if locked is None:
            raise Http404
        if locked.upload_status == UploadStatus.COMPLETED:
            return locked, UserProfile.objects.get(user=user)
        media = list(locked.media.all())
        for item in media:
            if item.upload_status == MediaStatus.VERIFIED:
                continue
            if item.pk in verified:
                item.upload_status, item.upload_error = MediaStatus.VERIFIED, ''
                item.width, item.height = verified[item.pk]
            elif item.pk in failures:
                item.upload_status, item.upload_error = MediaStatus.FAILED, failures[item.pk]
            item.save(update_fields=['upload_status', 'upload_error', 'width', 'height', 'updated_at'])
        if any(item.upload_status != MediaStatus.VERIFIED for item in media):
            locked.upload_status = UploadStatus.FAILED
            locked.upload_error = '仍有图片未通过验证，请检查上传状态。'
            profile = None
        else:
            locked.upload_status = UploadStatus.COMPLETED
            locked.upload_error = ''
            locked.points_awarded = reward_for(locked, media)
            profile = award_observation(locked, locked.points_awarded, completed=True)
        locked.upload_updated_at = timezone.now()
        locked.save(update_fields=['upload_status', 'upload_error', 'points_awarded', 'upload_updated_at'])
        return locked, profile


def upload_state(observation):
    complete = observation.upload_status == UploadStatus.COMPLETED
    return {
        'observationId': observation.pk, 'clientObservationId': observation.client_observation_id,
        'status': observation.upload_status, 'uploadError': observation.upload_error,
        'pointsAwarded': observation.points_awarded, 'retryable': not complete,
        'media': [
            dict(clientMediaId=item.client_media_id, objectKey=item.upload_key, type=item.kind,
                 pairGroupId=item.pair_group_id, status=item.upload_status, error=item.upload_error,
                 retryable=not complete and item.upload_status != MediaStatus.VERIFIED)
            for item in sorted(observation.media.all(), key=lambda entry: entry.pk)
        ],
    }


def describe_observation(observation, get_storage=None, *, detail=False):
    state = upload_state(observation)
    media = list(observation.media.all())
    paired = {ObservationMedia.Kind.RGB, ObservationMedia.Kind.THERMAL} <= {item.kind for item in media}
    state.update(
        title=observation.title, speciesName=observation.submitted_species_name,
        capturedAt=observation.captured_at, paired=paired,
        location=dict(longitude=observation.longitude, latitude=observation.latitude,
                      accuracy=observation.location_accuracy, source=observation.location_source)
        if observation.longitude is not None else None,
        rgbImageUrl=None, thermalImageUrl=None, thumbnailUrl=None,
    )
    if detail:
        state.update(description=observation.description, device=dict(
            phoneModel=observation.device_model, thermalDeviceModel=observation.thermal_device_model,
        ))
    if observation.upload_status != UploadStatus.COMPLETED or not media:
        return state
    get_storage = get_storage if get_storage is not None else storage_for_provider
    storage = get_storage(media[0].storage_provider)
    if detail:
        urls = {item.kind: storage.sign_download(item) for item in media}
        state.update(rgbImageUrl=urls.get('rgb'), thermalImageUrl=urls.get('thermal'),
                     thumbnailUrl=urls.get('thumbnail') or urls.get('rgb') or urls.get('thermal'))
    else:
        by_kind = {item.kind: item for item in media}
        thumb = by_kind.get('thumbnail') or by_kind.get('rgb') or by_kind.get('thermal')
        if thumb:
            state['thumbnailUrl'] = storage.sign_download(thumb)
    return state


@transaction.atomic
def delete_observation(user, observation_id):
    observation = owned_observations(user).select_for_update().filter(pk=observation_id).first()
    if not observation:
        if ObservationRecord.objects.filter(pk=observation_id, uploader=user,
                                            client_observation_id__isnull=False, deleted_at__isnull=False).exists():
            return
        raise Http404
    observation.deleted_at = timezone.now()
    observation.save(update_fields=['deleted_at'])
