"""Convert the supplied WGS84 Polygon/PolygonZ ZIP without simplifying borders."""
import argparse
import json
import tempfile
from pathlib import Path
from zipfile import ZipFile

from shapefile_readers import read_dbf, read_shp_polygons

ROOT = Path(__file__).resolve().parents[1]


def convert(source, output):
    with ZipFile(source) as archive:
        projection = archive.read('protectedArea.prj').decode('utf-8-sig')
        encoding = archive.read('protectedArea.cpg').decode('ascii').strip().upper()
        if 'GEOGCS["GCS_WGS_1984"' not in projection or encoding != 'UTF-8':
            raise ValueError('预期 WGS84 经纬度坐标与 UTF-8 属性编码，请先核实输入数据。')
        # Only copy known data members, never extract arbitrary archive paths.
        with tempfile.TemporaryDirectory(prefix='protected_area_') as temporary:
            path = Path(temporary) / 'protectedArea.shp'
            for suffix in ('shp', 'dbf'):
                path.with_suffix('.' + suffix).write_bytes(archive.read('protectedArea.' + suffix))
            attributes = read_dbf(path.with_suffix('.dbf'))
            geometries = read_shp_polygons(path)
    if len(attributes) != len(geometries):
        raise ValueError('属性记录数与空间要素数不一致。')
    features = []
    for index, (attributes, geometry) in enumerate(zip(attributes, geometries), 1):
        if not geometry['coordinates']:
            raise ValueError(f'第 {index} 个要素为空。')
        code = int(attributes.get('Num', '0'))
        if code not in (1, 2, 3):
            raise ValueError(f'第 {index} 个要素的 Num 分区编号无效。')
        # The source description field contains truncated HTML. Only expose
        # plain identifiers; do not render embedded markup or infer area units.
        features.append({'type': 'Feature', 'id': index,
                         'properties': {'name': attributes.get('Name') or f'图斑 {index}',
                                        'source_code': attributes.get('Num', ''), 'Num': code,
                                        'zone_type': {1:'核心区', 2:'缓冲区', 3:'实验区'}[code]},
                         'geometry': geometry})
    data = {'type': 'FeatureCollection', 'name': 'protected_areas', 'features': features}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(data, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    return len(features)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='将保护区压缩包转换为二维大屏 GeoJSON')
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=ROOT / 'app_monitor/static/app_monitor/geo/protected_areas.geojson')
    args = parser.parse_args()
    print(f'Converted {convert(args.input, args.output)} protected-area polygons: {args.output}')
