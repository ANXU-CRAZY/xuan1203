"""Restore real point detail from a reviewed, count-conserving local plan."""
import gzip
import hashlib
import json
import math
import os
from datetime import date
from pathlib import Path

from django.conf import settings
from django.contrib.gis.geos import Point
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.test import RequestFactory

from app_monitor.models import MapObservationCache, ObservationRecord, SpeciesInfo, WetlandZone
from app_monitor.monitoring import observations


def fingerprint(rows):
    # PostgreSQL float columns return 115.0 even if a reviewed plan uses 115.
    # Canonicalize representation without rounding away coordinate differences.
    canonical = [[*row[:5], float(row[5]), float(row[6])] for row in rows]
    return hashlib.sha256(json.dumps(sorted(canonical), ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def audit_rows():
    return [[pk, name, day.isoformat(), count, zone, lng, lat]
            for pk, name, day, count, zone, lng, lat in observations(RequestFactory().get('/')).values_list(
                'pk', 'species__name_cn', 'observation_time', 'count', 'zone__name', 'lng', 'lat')]


def identity(row):
    return [row[1], row[2], row[4]]


def validate_row(row):
    """Reject malformed plans before backups or any database mutation."""
    if not isinstance(row, list) or len(row) != 7:
        raise CommandError('明细字段格式无效')
    if (type(row[0]) is not int or row[0] <= 0 or type(row[3]) is not int or row[3] < 0
            or not isinstance(row[1], str) or not 1 <= len(row[1]) <= 100
            or not isinstance(row[4], str) or not 1 <= len(row[4]) <= 100):
        raise CommandError('明细标识、物种、区域或鸟类数量无效')
    try:
        if date.fromisoformat(row[2]).isoformat() != row[2]:
            raise ValueError
    except (TypeError, ValueError):
        raise CommandError('明细日期无效')
    x, y = row[5:7]
    if (type(x) not in (int, float) or type(y) not in (int, float)
            or not math.isfinite(x) or not math.isfinite(y)
            or not -180 <= x <= 180 or not -90 <= y <= 90):
        raise CommandError('明细坐标无效')


class Command(BaseCommand):
    help = '默认只核验。按已审核计划拆分旧区域汇总、纠正坐标、补齐缺失记录，保留线上独有数据。'

    def add_arguments(self, parser):
        parser.add_argument('--plan', type=Path, required=True)
        parser.add_argument('--apply', action='store_true')
        parser.add_argument('--backup-dir', type=Path)

    @transaction.atomic
    def handle(self, *args, **options):
        with gzip.open(options['plan'], 'rt', encoding='utf-8') as stream:
            plan = json.load(stream)
        if plan.get('version') != 2:
            raise CommandError('计划版本无效')
        applying = options['apply']
        # Validate the entire approved dataset, including all server-only rows.
        # A repeated apply or concurrent historical edit fails before any write.
        if applying:
            list(ObservationRecord.objects.filter(status='approved').select_for_update().values_list('pk', flat=True))
        before = audit_rows()
        if fingerprint(before) != plan['server_fingerprint']:
            raise CommandError('线上记录已变化或计划已执行，已停止；请重新比对')
        original = {r[0]: r for r in before}
        existing_groups = {tuple(identity(r)) for r in before}
        assigned, inserts, seen = {}, [], set()
        for group in plan['groups']:
            old, local = group['server'], group['local']
            key = group['identity']
            validate_row(old)
            for row in local:
                validate_row(row)
            if not local or original.get(old[0]) != old or identity(old) != key or old[0] in seen:
                raise CommandError('分组与线上原记录不一致')
            if sum(r[3] for r in local) != old[3] or any(identity(r) != key for r in local):
                raise CommandError('拆分前后物种/日期/区域或鸟类数量不守恒')
            seen.add(old[0])
            assigned[old[0]] = local[0]
            inserts.extend((row, old[0]) for row in local[1:])
        for row in plan['missing']:
            validate_row(row)
            if tuple(identity(row)) in existing_groups:
                raise CommandError('拟补充记录与线上已有分组重叠')
            inserts.append((row, None))
        all_details = list(assigned.values()) + [r for r, _ in inserts]
        keys = set()
        for row in all_details:
            x, y = row[5:7]
            key = tuple(identity(row)) + (x, y)
            if key in keys:
                raise CommandError('明细包含重复物种/日期/区域/位置')
            keys.add(key)
        predicted = [r for r in before if r[0] not in assigned] + list(assigned.values()) + [r for r, _ in inserts]
        actual = dict(records=len(predicted), birds=sum(r[3] for r in predicted),
                      locations=len({tuple(r[5:7]) for r in predicted}), species=len({r[1] for r in predicted}))
        if actual != plan['expected_after']:
            raise CommandError('计划完整统计不一致')
        result = dict(applied=applying, preserved_server_records=len(before)-len(assigned),
                      reconciled_groups=len(assigned), inserted_records=len(inserts), expected_after=actual)
        if not applying:
            self.stdout.write(json.dumps(result))
            return
        directory = options['backup_dir']
        if not directory or not directory.is_absolute() or directory.resolve().is_relative_to(Path(settings.BASE_DIR).resolve()):
            raise CommandError('必须指定项目目录之外的绝对备份目录')
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        records = {r.pk: r for r in ObservationRecord.objects.filter(pk__in=assigned)}
        cached = {r.pk: r for r in MapObservationCache.objects.filter(pk__in=assigned)}
        snapshot = []
        for pk, record in records.items():
            cache = cached.get(pk)
            snapshot.append(dict(id=pk, count=record.count, longitude=record.longitude, latitude=record.latitude,
                                 location=record.location.ewkt if record.location else None,
                                 cache=[cache.count, cache.longitude, cache.latitude] if cache else None))
        backup_path = directory / 'point-reconciliation-before.json.gz'
        with backup_path.open('xb') as file:
            os.chmod(backup_path, 0o600)
            with gzip.open(file, 'wt', encoding='utf-8') as stream:
                json.dump({'records': snapshot, 'plan_sha256': hashlib.sha256(options['plan'].read_bytes()).hexdigest()}, stream)
        species = {s.name_cn: s for s in SpeciesInfo.objects.all()}
        zones = {z.name: z for z in WetlandZone.objects.all()}
        for row, _ in inserts:
            if row[1] not in species:
                meta = plan['species_metadata'][row[1]]
                allowed = {'name_cn', 'name_latin', 'order', 'family', 'protection_level', 'distribution_habit'}
                if not isinstance(meta, dict) or set(meta) - allowed or meta.get('name_cn') != row[1]:
                    raise CommandError('补充物种元数据无效')
                species[row[1]] = SpeciesInfo.objects.create(**meta)
            if row[4] not in zones:
                zones[row[4]] = WetlandZone.objects.create(name=row[4], location=Point(row[5], row[6], srid=4326))
        for pk, row in assigned.items():
            record = records[pk]
            record.count, record.longitude, record.latitude = row[3], row[5], row[6]
            record.location = Point(row[5], row[6], srid=4326)
            if pk in cached:
                cached[pk].count, cached[pk].longitude, cached[pk].latitude = row[3], row[5], row[6]
        # Django constructs CASE expressions for every input object before
        # executing even when batch_size is set. Bound the outer inputs too.
        for model, objects, fields in (
            (ObservationRecord, list(records.values()), ['count', 'location', 'longitude', 'latitude']),
            (MapObservationCache, list(cached.values()), ['count', 'longitude', 'latitude']),
        ):
            for offset in range(0, len(objects), 1000):
                model.objects.bulk_update(objects[offset:offset + 1000], fields, batch_size=1000)
        new = [ObservationRecord(species=species[row[1]], zone=zones[row[4]], observation_time=date.fromisoformat(row[2]),
               count=row[3], location=Point(row[5], row[6], srid=4326), longitude=row[5], latitude=row[6], status='approved',
               uploader_id=records[parent].uploader_id if parent else None,
               reporter_id=records[parent].reporter_id if parent else None) for row, parent in inserts]
        ObservationRecord.objects.bulk_create(new, batch_size=1000)
        MapObservationCache.objects.bulk_create([MapObservationCache(record=r, observation_time=r.observation_time,
            count=r.count, status=r.status, species_id_cached=r.species_id, species_name=r.species.name_cn,
            species_latin=r.species.name_latin, species_protection=r.species.protection_level,
            zone_id_cached=r.zone_id, zone_name=r.zone.name, longitude=r.longitude, latitude=r.latitude,
            transect_name=cached[parent].transect_name if parent in cached else '')
            for r, (_, parent) in zip(new, inserts)], batch_size=1000)
        after = audit_rows()
        verified = dict(records=len(after), birds=sum(r[3] for r in after),
                        locations=len({tuple(r[5:7]) for r in after}), species=len({r[1] for r in after}))
        if verified != actual:
            raise CommandError('写入后校验失败，事务已回滚')
        expected_rows = [r for r in before if r[0] not in assigned]
        expected_rows.extend([[pk, *row[1:]] for pk, row in assigned.items()])
        expected_rows.extend([[record.pk, *row[1:]] for record, (row, _) in zip(new, inserts)])
        if fingerprint(after) != fingerprint(expected_rows):
            raise CommandError('写入后逐条坐标/数量核验失败，事务已回滚')
        result.update(verified=verified, backup=str(backup_path), inserted_ids=[r.pk for r in new])
        result_path = directory / 'point-reconciliation-applied.json'
        with result_path.open('x', encoding='utf-8') as stream:
            os.chmod(result_path, 0o600)
            json.dump(result, stream)
        self.stdout.write(json.dumps({k: v for k, v in result.items() if k != 'inserted_ids'}))
