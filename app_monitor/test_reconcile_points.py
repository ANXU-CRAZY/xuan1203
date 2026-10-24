"""Destructive maintenance contracts exercised only in an isolated PostGIS DB."""
import copy
import gzip
import hashlib
import io
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth.models import User
from django.contrib.gis.geos import Point
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from .management.commands.reconcile_observation_points import audit_rows, fingerprint
from .models import MapObservationCache, ObservationRecord, SpeciesInfo, WetlandZone
from .protection import normalize_protection_level


class ReconcilePointsTests(TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='reconcile-contract-')
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.user = User.objects.create_user(username='point-uploader')
        self.species = SpeciesInfo.objects.create(name_cn='待细分鸟', protection_level='国家二级')
        self.unique = SpeciesInfo.objects.create(name_cn='线上独有鸟')
        self.zone = WetlandZone.objects.create(name='旧城市点', longitude=114, latitude=35)
        self.old = ObservationRecord.objects.create(species=self.species, zone=self.zone,
            observation_time='2024-01-01', count=10, status='approved',
            location=Point(114, 35, srid=4326), image='observations/preserve.jpg',
            description='线上照片与说明必须保留', uploader=self.user, reporter=self.user)
        self.server_only = ObservationRecord.objects.create(species=self.unique, zone=self.zone,
            observation_time='2024-02-01', count=3, status='approved', location=Point(116, 35, srid=4326))
        self.pending = ObservationRecord.objects.create(species=self.species, zone=self.zone,
            observation_time='2024-01-01', count=99, status='pending', location=Point(114, 35, srid=4326))
        self.cache = MapObservationCache.objects.create(record=self.old,
            observation_time=self.old.observation_time, count=10, status='approved',
            species_id_cached=self.species.pk, species_name=self.species.name_cn,
            species_protection=self.species.protection_level, zone_id_cached=self.zone.pk,
            zone_name=self.zone.name, longitude=114, latitude=35,
            transect_name='原样线', image_url='/media/observations/preserve.jpg', description='原缓存说明')
        before = audit_rows()
        old = next(r for r in before if r[0] == self.old.pk)
        first, second = old.copy(), old.copy()
        first[0], first[3], first[5] = 10001, 4, 114.1
        second[0], second[3], second[5] = 10002, 6, 114.2
        self.plan = dict(version=2, server_fingerprint=fingerprint(before),
            groups=[dict(identity=[old[1], old[2], old[4]], server=old, local=[first, second])],
            missing=[[10003, '补充鸟', '2024-03-01', 2, '新湿地', 115, 35]],
            species_metadata={'补充鸟': dict(name_cn='补充鸟', name_latin='Test bird', protection_level='国家一级')},
            expected_after=dict(records=4, birds=15, locations=4, species=3))

    def run_plan(self, plan=None, apply=False, backup=True):
        path = self.directory / 'plan.json.gz'
        with gzip.open(path, 'wt', encoding='utf-8') as stream:
            json.dump(plan if plan is not None else self.plan, stream)
        options = dict(plan=path, stdout=io.StringIO())
        if apply:
            options['apply'] = True
        if backup:
            options['backup_dir'] = self.directory / 'backup'
        call_command('reconcile_observation_points', **options)
        return json.loads(options['stdout'].getvalue())

    def snapshot(self):
        return list(ObservationRecord.objects.order_by('pk').values()), list(MapObservationCache.objects.order_by('pk').values())

    def test_default_is_dry_run_without_backup_or_writes(self):
        before = self.snapshot()
        result = self.run_plan(backup=False)
        self.assertFalse(result['applied'])
        self.assertEqual(result['inserted_records'], 2)
        self.assertEqual(self.snapshot(), before)
        self.assertFalse((self.directory / 'backup').exists())

    def test_apply_conserves_birds_retains_server_data_and_personal_metadata(self):
        server_only = ObservationRecord.objects.get(pk=self.server_only.pk).__dict__.copy()
        result = self.run_plan(apply=True)
        self.assertEqual(result['verified'], self.plan['expected_after'])
        self.assertEqual(ObservationRecord.objects.count(), 5)  # pending row stays untouched
        self.old.refresh_from_db()
        self.cache.refresh_from_db()
        self.assertEqual((self.old.count, self.old.longitude, self.old.location.x), (4, 114.1, 114.1))
        self.assertEqual(str(self.old.image), 'observations/preserve.jpg')
        self.assertEqual(self.old.description, '线上照片与说明必须保留')
        self.assertEqual((self.old.uploader_id, self.old.reporter_id), (self.user.pk, self.user.pk))
        self.assertEqual((self.cache.count, self.cache.longitude), (4, 114.1))
        self.assertEqual(self.cache.image_url, '/media/observations/preserve.jpg')
        self.assertEqual(self.cache.description, '原缓存说明')
        split = ObservationRecord.objects.get(longitude=114.2)
        self.assertEqual((split.count, split.uploader_id, split.reporter_id), (6, self.user.pk, self.user.pk))
        self.assertEqual(split.map_cache.transect_name, '原样线')
        self.assertFalse(split.image)
        missing = ObservationRecord.objects.get(species__name_cn='补充鸟')
        self.assertIsNone(missing.uploader_id)
        self.assertEqual(missing.zone.name, '新湿地')
        self.assertEqual(missing.zone.location.x, 115)
        self.assertEqual(missing.map_cache.count, 2)
        self.assertEqual(missing.species.protection_level, normalize_protection_level('国家一级'))
        self.server_only.refresh_from_db()
        for field, value in server_only.items():
            if field != '_state':
                self.assertEqual(getattr(self.server_only, field), value)
        self.pending.refresh_from_db()
        self.assertEqual((self.pending.count, self.pending.status, self.pending.longitude), (99, 'pending', 114))

    def test_backup_precedes_mutation_and_tracks_inserted_ids(self):
        self.run_plan(apply=True)
        path = self.directory / 'backup' / 'point-reconciliation-before.json.gz'
        with gzip.open(path, 'rt', encoding='utf-8') as stream:
            saved = json.load(stream)
        self.assertEqual(saved['records'][0]['count'], 10)
        self.assertEqual(saved['records'][0]['longitude'], 114)
        self.assertEqual(saved['records'][0]['cache'], [10, 114, 35])
        self.assertEqual(saved['plan_sha256'], hashlib.sha256((self.directory / 'plan.json.gz').read_bytes()).hexdigest())
        applied = json.loads((self.directory / 'backup' / 'point-reconciliation-applied.json').read_text())
        self.assertEqual(set(applied['inserted_ids']), set(ObservationRecord.objects.filter(pk__gt=self.pending.pk).values_list('pk', flat=True)))

    def test_repeated_apply_rejected_before_second_write(self):
        self.run_plan(apply=True)
        before = self.snapshot()
        with self.assertRaisesMessage(CommandError, '线上记录已变化或计划已执行'):
            self.run_plan(apply=True)
        self.assertEqual(self.snapshot(), before)

    def test_stale_plan_and_count_changes_rejected(self):
        ObservationRecord.objects.filter(pk=self.server_only.pk).update(count=4)
        before = self.snapshot()
        with self.assertRaisesMessage(CommandError, '线上记录已变化或计划已执行'):
            self.run_plan(apply=True)
        self.assertEqual(self.snapshot(), before)

    def test_group_bird_count_must_be_conserved(self):
        self.plan['groups'][0]['local'][0][3] += 1
        before = self.snapshot()
        with self.assertRaisesMessage(CommandError, '鸟类数量不守恒'):
            self.run_plan(apply=True)
        self.assertEqual(self.snapshot(), before)

    def test_missing_group_overlap_and_duplicate_point_are_rejected(self):
        duplicate = copy.deepcopy(self.plan)
        duplicate['groups'][0]['local'][1][5] = 114.1
        with self.assertRaisesMessage(CommandError, '重复物种/日期/区域/位置'):
            self.run_plan(duplicate)
        overlap = copy.deepcopy(self.plan)
        overlap['missing'] = [overlap['groups'][0]['local'][0]]
        with self.assertRaisesMessage(CommandError, '与线上已有分组重叠'):
            self.run_plan(overlap)

    def test_invalid_coordinates_counts_and_dates_rejected(self):
        for index, invalid in ((5, float('nan')), (5, 181), (6, None), (3, True), (2, '2024-02-31')):
            with self.subTest(index=index, value=invalid):
                plan = copy.deepcopy(self.plan)
                plan['missing'][0][index] = invalid
                with self.assertRaises(CommandError):
                    self.run_plan(plan, apply=True)
        self.assertEqual(ObservationRecord.objects.count(), 3)

    def test_apply_requires_backup_outside_project(self):
        with self.assertRaisesMessage(CommandError, '绝对备份目录'):
            self.run_plan(apply=True, backup=False)
        self.assertEqual(ObservationRecord.objects.count(), 3)

    def test_postwrite_total_failure_rolls_back_records_cache_species_and_zone(self):
        before = self.snapshot()
        original = audit_rows()
        with patch('app_monitor.management.commands.reconcile_observation_points.audit_rows', side_effect=[original, original]):
            with self.assertRaisesMessage(CommandError, '写入后校验失败'):
                self.run_plan(apply=True)
        self.assertEqual(self.snapshot(), before)
        self.assertFalse(SpeciesInfo.objects.filter(name_cn='补充鸟').exists())
        self.assertFalse(WetlandZone.objects.filter(name='新湿地').exists())

    def test_wrong_coordinates_with_same_totals_roll_back(self):
        before = self.snapshot()
        original_audit = audit_rows
        calls = 0

        def wrong_after():
            nonlocal calls
            calls += 1
            rows = original_audit()
            if calls > 1:
                # Four distinct coordinates and all totals remain unchanged.
                next(r for r in rows if r[0] == self.old.pk)[5] += .01
            return rows

        with patch('app_monitor.management.commands.reconcile_observation_points.audit_rows', side_effect=wrong_after):
            with self.assertRaisesMessage(CommandError, '逐条坐标/数量核验失败'):
                self.run_plan(apply=True)
        self.assertEqual(self.snapshot(), before)

    def test_species_metadata_cannot_inject_ids_or_file_fields(self):
        self.plan['species_metadata']['补充鸟']['id'] = self.species.pk
        with self.assertRaisesMessage(CommandError, '物种元数据无效'):
            self.run_plan(apply=True)
        self.assertEqual(ObservationRecord.objects.count(), 3)
