import math
from pathlib import PurePosixPath

from django.conf import settings
from rest_framework import serializers

from .contribution_storage import IMAGE_FORMATS
from .models import ObservationMedia


class LocationInput(serializers.Serializer):
    longitude = serializers.FloatField(min_value=-180, max_value=180)
    latitude = serializers.FloatField(min_value=-90, max_value=90)
    accuracy = serializers.FloatField(min_value=0, max_value=100_000, required=False)
    source = serializers.CharField(max_length=30, required=False, allow_blank=True)

    def validate(self, data):
        if not all(math.isfinite(data[key]) for key in ('longitude', 'latitude', 'accuracy') if key in data):
            raise serializers.ValidationError('坐标和定位精度必须是有限数值。')
        return data


class DeviceInput(serializers.Serializer):
    phoneModel = serializers.CharField(max_length=100, required=False, allow_blank=True)
    thermalDeviceModel = serializers.CharField(max_length=100, required=False, allow_blank=True)


class MediaInput(serializers.Serializer):
    clientMediaId = serializers.UUIDField()
    type = serializers.ChoiceField(choices=ObservationMedia.Kind.values)
    pairGroupId = serializers.UUIDField()
    filename = serializers.RegexField(r'^[^/\\\x00-\x1f\x7f]+$', max_length=200)
    mimeType = serializers.ChoiceField(choices=tuple(IMAGE_FORMATS))
    fileSize = serializers.IntegerField(min_value=1)
    sha256 = serializers.RegexField(r'\A[0-9a-fA-F]{64}\Z', max_length=64)

    def validate(self, data):
        if data['fileSize'] > settings.CONTRIBUTION_MAX_IMAGE_BYTES:
            raise serializers.ValidationError({'fileSize': '单张图片超过大小限制。'})
        if PurePosixPath(data['filename']).suffix.lower() not in IMAGE_FORMATS[data['mimeType']][1]:
            raise serializers.ValidationError({'filename': '文件扩展名与图片类型不匹配。'})
        data['sha256'] = data['sha256'].lower()
        return data


class UploadSessionInput(serializers.Serializer):
    clientObservationId = serializers.UUIDField()
    title = serializers.CharField(max_length=120)
    description = serializers.CharField(max_length=4000, required=False, default='', allow_blank=True)
    speciesName = serializers.CharField(max_length=100, required=False, default='', allow_blank=True)
    capturedAt = serializers.DateTimeField()
    location = LocationInput(required=False, default=dict, allow_null=True)
    device = DeviceInput(required=False, default=dict)
    media = MediaInput(many=True, allow_empty=False, max_length=3)

    def validate_media(self, media):
        if len({item['clientMediaId'] for item in media}) != len(media):
            raise serializers.ValidationError('图片编号不能重复。')
        kinds = {item['type'] for item in media}
        if len(kinds) != len(media) or kinds == {ObservationMedia.Kind.THUMBNAIL}:
            raise serializers.ValidationError('必须包含 RGB 或红外原图，每种类型最多一张。')
        if len({item['pairGroupId'] for item in media}) != 1:
            raise serializers.ValidationError('同一次观测的图片必须使用同一个配对编号。')
        return sorted(media, key=lambda item: item['type'])

    def validate(self, data):
        data['location'] = data['location'] or {}
        return data


class CompletedMediaInput(serializers.Serializer):
    clientMediaId = serializers.UUIDField()
    objectKey = serializers.CharField(max_length=300)
    sha256 = serializers.RegexField(r'\A[0-9a-fA-F]{64}\Z', max_length=64)


class CompleteInput(serializers.Serializer):
    media = CompletedMediaInput(many=True, allow_empty=False, max_length=3)
