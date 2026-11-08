"""Small, image-backed catalog for games, independent of observation statistics."""
from django.db.models import Prefetch
from django.core.exceptions import SuspiciousFileOperation
from django.http import JsonResponse
from django.views.decorators.http import require_GET

from .models import SpeciesImage, SpeciesInfo
from .protection import normalize_protection_level


def _existing_image(field, request):
    if not field or str(field) in {'', 'False', 'None'}:
        return None
    try:
        if field.storage.exists(field.name):
            return request.build_absolute_uri(field.url)
    except (OSError, ValueError, SuspiciousFileOperation):
        pass
    return None


@require_GET
def birds(request):
    # The full species serializer counts observations and fetches several
    # related objects per species. Games need none of those expensive queries.
    species = SpeciesInfo.objects.only('id', 'name_cn', 'name_latin', 'order',
        'protection_level', 'distribution_habit', 'cover_image').order_by('id').prefetch_related(
            Prefetch('images', queryset=SpeciesImage.objects.only('id', 'species_id', 'image', 'caption', 'is_featured').order_by('-is_featured', 'id')))
    result = []
    for bird in species:
        images = []
        seen = set()
        cover = _existing_image(bird.cover_image, request)
        for image in bird.images.all():
            url = _existing_image(image.image, request)
            if url and url not in seen:
                images.append({'id': image.id, 'species': bird.id, 'url': url, 'caption': image.caption})
                seen.add(url)
        if cover and cover not in seen:
            images.insert(0, {'species': bird.id, 'url': cover, 'caption': bird.name_cn})
        if not images:
            continue
        result.append({'id': bird.id, 'name_cn': bird.name_cn, 'name_latin': bird.name_latin,
            'order': bird.order, 'protection_level': normalize_protection_level(bird.protection_level),
            'distribution_habit': bird.distribution_habit, 'description': bird.distribution_habit,
            'cover_image_url': images[0]['url'], 'gallery_images': images, 'gallery_count': len(images)})
    return JsonResponse({'results': result, 'count': len(result),
                         'image_count': sum(len(bird['gallery_images']) for bird in result)})
