from django.middleware.locale import LocaleMiddleware
from django.utils import translation


class PlatformLocaleMiddleware(LocaleMiddleware):
    def process_request(self, request):
        super().process_request(request)
        if request.path_info.startswith('/admin/'):
            translation.activate('zh-hans')
            request.LANGUAGE_CODE = 'zh-hans'
