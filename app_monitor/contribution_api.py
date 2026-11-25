from functools import cache

from django.shortcuts import get_object_or_404
from rest_framework import permissions, serializers, status, viewsets
from rest_framework.parsers import JSONParser
from rest_framework.response import Response

from . import contributions
from .contribution_points import contribution_profile
from .contribution_serializers import CompleteInput, UploadSessionInput
from .contribution_storage import StorageUnavailable, storage_for_provider
from .models import ObservationRecord, UserProfile


class MineQuery(serializers.Serializer):
    page = serializers.IntegerField(default=1, min_value=1, max_value=1_000_000)
    pageSize = serializers.IntegerField(default=20, min_value=1, max_value=50)
    status = serializers.ChoiceField(choices=ObservationRecord.UploadStatus.values, required=False)


class ContributionViewSet(viewsets.ViewSet):
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [JSONParser]

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response['Cache-Control'] = 'private, no-store'
        return response

    def handle_exception(self, exc):
        if isinstance(exc, StorageUnavailable):
            return Response({'error': '对象存储暂不可用，请稍后重试。'}, status=503)
        if isinstance(exc, contributions.ManifestConflict):
            return Response({'error': '请求与该观测的原始上传清单不一致。'}, status=409)
        return super().handle_exception(exc)

    def _owned(self, request, observation_id):
        return get_object_or_404(contributions.owned_observations(request.user).prefetch_related('media'),
                                 pk=observation_id)

    def start(self, request):
        serializer = UploadSessionInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        record, uploads, created = contributions.upload_session(request.user, serializer.validated_data)
        return Response({'observationId': record.pk, 'status': record.upload_status, 'uploads': uploads},
                        status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)

    def complete(self, request, observation_id):
        record = self._owned(request, observation_id)
        serializer = CompleteInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        record, profile = contributions.complete_observation(request.user, record, serializer.validated_data['media'])
        response = contributions.upload_state(record)
        if profile is None:
            return Response(response, status=409)
        response.update(contribution_profile(profile))
        return Response(response)

    def upload_status(self, request, observation_id):
        return Response(contributions.upload_state(self._owned(request, observation_id)))

    def mine(self, request):
        serializer = MineQuery(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        params = serializer.validated_data
        queryset = contributions.owned_observations(request.user).prefetch_related('media').order_by('-pk')
        if 'status' in params:
            queryset = queryset.filter(upload_status=params['status'])
        page, size = params['page'], params['pageSize']
        offset = (page - 1) * size
        records = list(queryset[offset:offset + size])
        get_storage = cache(storage_for_provider)
        return Response({
            'count': queryset.count(), 'page': page, 'pageSize': size,
            'results': [contributions.describe_observation(item, get_storage) for item in records],
        })

    def retrieve(self, request, observation_id):
        return Response(contributions.describe_observation(self._owned(request, observation_id), detail=True))

    def destroy(self, request, observation_id):
        contributions.delete_observation(request.user, observation_id)
        return Response(status=204)

    def profile(self, request):
        profile, _ = UserProfile.objects.get_or_create(user=request.user)
        return Response(contribution_profile(profile))
