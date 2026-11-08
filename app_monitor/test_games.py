from pathlib import Path
from tempfile import TemporaryDirectory

from django.test import TestCase, override_settings

from .models import SpeciesImage, SpeciesInfo


class GameCatalogTests(TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.override = override_settings(MEDIA_ROOT=self.directory.name)
        self.override.enable()
        self.addCleanup(self.override.disable)
        root = Path(self.directory.name) / 'species'
        root.mkdir()
        (root / 'bird.jpg').write_bytes(b'local image fixture')

    def test_missing_and_remote_images_are_not_quiz_questions(self):
        available = SpeciesInfo.objects.create(name_cn='白鹭', cover_image='species/bird.jpg')
        missing = SpeciesInfo.objects.create(name_cn='苍鹭', cover_image='species/missing.jpg')
        SpeciesImage.objects.create(species=missing, image_url='https://example.com/bird.jpg')
        SpeciesInfo.objects.create(name_cn='大天鹅')
        response = self.client.get('/api/games/birds/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual([row['id'] for row in response.json()['results']], [available.id])
        self.assertEqual(response.json()['image_count'], 1)

    def test_catalog_uses_two_queries_and_deduplicates_photos(self):
        for index in range(8):
            bird = SpeciesInfo.objects.create(name_cn=f'物种{index}', cover_image='species/bird.jpg')
            SpeciesImage.objects.create(species=bird, image='species/bird.jpg')
        with self.assertNumQueries(2):
            response = self.client.get('/api/games/birds/')
        self.assertEqual(response.json()['count'], 8)
        self.assertTrue(all(len(row['gallery_images']) == 1 for row in response.json()['results']))
