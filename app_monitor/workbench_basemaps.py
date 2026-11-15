"""Local provider styles, using ignored configuration rather than committed keys."""
import json
import math
from pathlib import Path
from urllib.parse import urlencode


def provider_config(base_dir):
    path = Path(base_dir) / 'var/geolibre/providers.json'
    return json.loads(path.read_text(encoding='utf-8')) if path.is_file() else {}


def gcj_offset(lng, lat):
    if not (72.004 < lng < 137.8347 and .8293 < lat < 55.8271):
        return 0, 0
    x, y = lng - 105, lat - 35
    a = -100 + 2*x + 3*y + .2*y*y + .1*x*y + .2*math.sqrt(abs(x))
    b = 300 + x + 2*y + .1*x*x + .1*x*y + .1*math.sqrt(abs(x))
    a += (20*math.sin(6*x*math.pi) + 20*math.sin(2*x*math.pi))*2/3
    a += (20*math.sin(y*math.pi) + 40*math.sin(y*math.pi/3))*2/3
    a += (160*math.sin(y*math.pi/12) + 320*math.sin(y*math.pi/30))*2/3
    b += (20*math.sin(6*x*math.pi) + 20*math.sin(2*x*math.pi))*2/3
    b += (20*math.sin(x*math.pi) + 40*math.sin(x*math.pi/3))*2/3
    b += (150*math.sin(x*math.pi/12) + 300*math.sin(x*math.pi/30))*2/3
    rad = lat * math.pi / 180
    magic = 1 - .00669342162296594323 * math.sin(rad)**2
    return b*180/(6378245/math.sqrt(magic)*math.cos(rad)*math.pi), a*180/(6378245*(1-.00669342162296594323)/(magic**1.5)*math.pi)


def wgs_to_gcj(lng, lat):
    x, y = gcj_offset(lng, lat)
    return lng + x, lat + y


def gcj_to_wgs(lng, lat):
    x, y = lng, lat
    for _ in range(5):
        gx, gy = wgs_to_gcj(x, y)
        x -= gx - lng; y -= gy - lat
    return [x, y]


def make_style(config, kind='vector', labels=True, center=(113.58, 34.96), zoom=10, width=1024, height=768):
    style = {'version': 8, 'name': '方舟底图', 'sources': {},
             'layers': [{'id': 'paper', 'type': 'background', 'paint': {'background-color': '#f3f6f1'}}]}
    if kind == 'blank':
        return style
    if kind == 'amap':
        key = config.get('amap_key')
        if not key:
            raise ValueError('高德地图尚未配置。')
        scale = max(width/1024, height/1024, 1)
        z = max(1, min(18, math.floor(zoom-math.log2(scale))))
        ratio = 2**(zoom-z)
        w, h = max(64, min(1024, math.ceil(width/ratio))), max(64, min(1024, math.ceil(height/ratio)))
        lng, lat = wgs_to_gcj(*center)
        world = 256*2**z
        px = (lng+180)/360*world
        py = (1-math.asinh(math.tan(math.radians(lat)))/math.pi)/2*world
        corners = []
        for dx, dy in [(-w/2,-h/2),(w/2,-h/2),(w/2,h/2),(-w/2,h/2)]:
            x = (px+dx)/world*360-180
            y = math.degrees(math.atan(math.sinh(math.pi*(1-2*(py+dy)/world))))
            corners.append(gcj_to_wgs(x, y))
        url = 'https://restapi.amap.com/v3/staticmap?' + urlencode({'key': key, 'location': f'{lng:.7f},{lat:.7f}', 'zoom': z, 'size': f'{w}*{h}', 'scale': 2})
        style['sources']['amap'] = {'type': 'image', 'url': url, 'coordinates': corners}
        style['metadata'] = {'arkAttribution': '© 高德地图'}
        style['layers'].append({'id': 'amap', 'type': 'raster', 'source': 'amap', 'paint': {'raster-fade-duration': 0}})
        return style
    if kind not in ('vector', 'imagery'):
        raise ValueError('不支持的底图。')
    key = config.get('tianditu_key')
    if not key:
        raise ValueError('天地图尚未配置。')
    names = ['vec' if kind == 'vector' else 'img']
    if labels:
        names.append('cva' if kind == 'vector' else 'cia')
    for name in names:
        tiles = [f'https://t{s}.tianditu.gov.cn/{name}_w/wmts?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0&LAYER={name}&STYLE=default&TILEMATRIXSET=w&FORMAT=tiles&TILEMATRIX={{z}}&TILEROW={{y}}&TILECOL={{x}}&tk={key}' for s in range(8)]
        style['sources'][name] = {'type': 'raster', 'tiles': tiles, 'tileSize': 256, 'maxzoom': 18, 'attribution': '© 天地图' if name == names[0] else ''}
        style['layers'].append({'id': name, 'type': 'raster', 'source': name, 'paint': {'raster-fade-duration': 0}})
    return style
