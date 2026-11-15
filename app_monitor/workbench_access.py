"""Access policy shared by the local and deployed workbench services."""
from django.conf import settings


def is_local(request):
    return (not getattr(settings, 'GEOSTUDIO_REMOTE_COMPUTE', False) and
            request.get_host().split(':')[0] in {'127.0.0.1', 'localhost'} and
            request.META.get('REMOTE_ADDR') in {'127.0.0.1', '::1'})


def may_compute(request):
    return is_local(request) or (
        getattr(settings, 'GEOSTUDIO_REMOTE_COMPUTE', False)
        and request.user.is_authenticated and request.user.is_active
    )


def owner_id(request):
    return 'local' if is_local(request) else str(request.user.pk)
