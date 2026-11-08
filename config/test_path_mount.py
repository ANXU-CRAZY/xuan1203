import io
import unittest
from config.path_mount import PlatformMount, mount_location, rewrite_text


class PathMountTests(unittest.TestCase):
    def test_legacy_paths_and_generated_urls_are_not_double_prefixed(self):
        value = '''<a href="/"><img src="/static/a.png"><a href="/platform/admin/">'''
        self.assertEqual(rewrite_text(value, html=True), '''<a href="/platform/"><img src="/platform/static/a.png"><a href="/platform/admin/">''')

    def test_external_map_urls_and_vendor_delimiters_are_preserved(self):
        text = '''fetch('//t0.tianditu.gov.cn'); const slash='/'; const url='/api/foo/'; url(/static/a.png)'''
        self.assertEqual(rewrite_text(text), '''fetch('//t0.tianditu.gov.cn'); const slash='/'; const url='/platform/api/foo/'; url(/platform/static/a.png)''')

    def test_laboratory_link_points_to_domain_root(self):
        self.assertEqual(rewrite_text('href="https://3.1415926.love/arklb-geoai/"', html=True), 'href="/"')
        self.assertEqual(mount_location('/admin/login/?next=/platform/admin/'), '/platform/admin/login/?next=/platform/admin/')

    def test_html_inline_non_url_slashes_are_preserved(self):
        text = '''<span separator="/">'+a+'/'+b; url.replace('/thumb/','/'); <a href="https://3.1415926.love">'''
        self.assertEqual(rewrite_text(text, html=True), '''<span separator="/">'+a+'/'+b; url.replace('/thumb/','/'); <a href="/platform/">''')

    def test_api_suffix_is_not_prefixed_twice(self):
        text = "const API='/api'; fetch(API + '/login/'); fetch(API+'/species/'); fetch('/species/');"
        self.assertEqual(rewrite_text(text,html=True), "const API='/platform/api'; fetch(API + '/login/'); fetch(API+'/species/'); fetch('/platform/species/');")

    def test_absolute_media_and_pagination_urls(self):
        text = '{"photo":"https://arklab-geoai.org.cn/media/a.jpg","next":"https://arklab-geoai.org.cn/platform/api/species/?page=2"}'
        self.assertEqual(rewrite_text(text), '{"photo":"https://arklab-geoai.org.cn/platform/media/a.jpg","next":"https://arklab-geoai.org.cn/platform/api/species/?page=2"}')

    def test_host_scoped_mount_and_legacy_isolation(self):
        captured = []
        app = PlatformMount(lambda e, s: captured.append((e['SCRIPT_NAME'],e['PATH_INFO'])))
        for host in ['arklab-geoai.org.cn','3.1415926.love']:
            app({'HTTP_HOST':host,'SCRIPT_NAME':'','PATH_INFO':'/platform/login/','wsgi.input':io.BytesIO()},None)
        self.assertEqual(captured,[('/platform','/login/'),('','/platform/login/')])


if __name__ == '__main__':
    unittest.main()
