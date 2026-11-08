"""Mount the existing platform below /platform on the laboratory domain only.

Keep legacy domains at their existing root. SCRIPT_NAME makes Django-generated
URLs (admin, redirects, API pagination) correct; response adaptation covers the
legacy templates' literal root URLs. Static assets use the same rewrite helper
when building the domain-specific static overlay; original assets stay intact.
"""
import re

DOMAINS = {'arklab-geoai.org.cn', 'www.arklab-geoai.org.cn'}
PREFIX = '/platform'
ROOTS = (
    'api', 'static', 'media', 'huiyan', 'admin', 'login', 'profile', 'report',
    'species', 'articles', 'gallery', 'image-gallery', 'bird', 'bird-page',
    'bird-guess', 'bird-runner', 'wetland-restorer', 'migration',
    'wetland-detective', 'floating-island', 'WMTX', 'wmtx', 'accounts',
)
ROOT_URL = re.compile(r'''(?P<lead>["'`(=])/(?P<path>''' + '|'.join(ROOTS) + r''')(?=[/"'`?#)\s]|$)''')
HOME_URL = re.compile(r'''(?P<lead>\b(?:href|action)\s*=\s*["'])/(?=["'?#])''', re.I)
LAB_URL = re.compile(r'https?://(?:3\.1415926\.love|8\.130\.88\.229)/(?:arklab|arklb)-geoai/?(?=["\s\x27`<>?#]|$)')
OLD_ORIGIN = re.compile(r'https?://(?:3\.1415926\.love|8\.130\.88\.229)(?=/|["\x27`\s<>]|$)')
DOMAIN_ROOT_URL = re.compile(r'(https?://(?:www\.)?arklab-geoai\.org\.cn)/(?=' + '|'.join(root + r'(?:/|["\x27?#]|$)' for root in ROOTS) + ')')


def rewrite_text(text, *, html=False):
    # A temporary marker prevents the laboratory root from being prefixed.
    marker = '__ARK_LAB_HOME_20261025__'
    text = LAB_URL.sub(marker, text)
    text = OLD_ORIGIN.sub(lambda m: PREFIX if text[m.end():m.end()+1] == '/' else PREFIX + '/', text)
    text = DOMAIN_ROOT_URL.sub(lambda m: m[1] + PREFIX + '/', text)
    def root_url(match):
        # API + '/login/' is a suffix of an already mounted API base.
        previous = match.start() - 1
        while previous >= 0 and text[previous].isspace():
            previous -= 1
        if previous >= 0 and text[previous] == '+':
            return match.group(0)
        return match['lead'] + PREFIX + '/' + match['path']
    text = ROOT_URL.sub(root_url, text)
    if html:
        text = HOME_URL.sub(lambda m: m['lead'] + PREFIX + '/', text)
    return text.replace(marker, '/')


def mount_location(value):
    if LAB_URL.fullmatch(value):
        return '/'
    value = OLD_ORIGIN.sub('', value)
    if value.startswith('/') and not value.startswith(('//', PREFIX + '/')) and value != PREFIX:
        return PREFIX + value
    return value


def configure_domain_mount():
    from django.conf import settings
    settings.ALLOWED_HOSTS = list(dict.fromkeys([*settings.ALLOWED_HOSTS, *sorted(DOMAINS)]))
    name = 'config.path_mount.PlatformResponseMiddleware'
    settings.MIDDLEWARE = [name, *[m for m in settings.MIDDLEWARE if m != name]]
    # Every existing Nginx proxy overwrites this header; gunicorn is Unix-only.
    settings.SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')


class PlatformMount:
    def __init__(self, application):
        self.application = application

    def __call__(self, environ, start_response):
        host = environ.get('HTTP_HOST', '').split(':')[0].lower().rstrip('.')
        path = environ.get('PATH_INFO', '')
        if host in DOMAINS and path.startswith(PREFIX + '/'):
            environ['SCRIPT_NAME'] = PREFIX
            environ['PATH_INFO'] = path[len(PREFIX):]
            environ['ark.platform_mount'] = True
        return self.application(environ, start_response)


class PlatformResponseMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if not request.META.get('ark.platform_mount'):
            return response
        from django.utils.cache import patch_vary_headers
        patch_vary_headers(response, ['Host'])
        if response.has_header('Location'):
            response['Location'] = mount_location(response['Location'])
        for cookie in response.cookies.values():
            path = cookie['path']
            if path.startswith('/') and not path.startswith(PREFIX + '/'):
                cookie['path'] = PREFIX + path
        kind = response.get('Content-Type', '').split(';')[0]
        if not response.streaming and not response.has_header('Content-Encoding') and kind in {
            'text/html', 'application/json', 'application/javascript', 'text/javascript', 'text/css',
        }:
            old = response.content
            body = rewrite_text(old.decode(response.charset), html=kind == 'text/html').encode(response.charset)
            if body != old:
                response.content = body
                if response.has_header('Content-Length'):
                    response['Content-Length'] = str(len(body))
                for header in ('ETag', 'Content-MD5'):
                    if response.has_header(header):
                        del response[header]
        return response
