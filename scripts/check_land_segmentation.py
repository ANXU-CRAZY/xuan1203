"""Exercise the host integration with a real image; leaves its workspace empty.

python scripts/check_land_segmentation.py --image path/to/image.jpg \
    --box 100 100 800 800 --output tmp/land-overlay.png
"""
import argparse
import csv
import http.cookiejar
import io
import json
from pathlib import Path
import urllib.request


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', default='http://127.0.0.1:8012')
    parser.add_argument('--image', type=Path, required=True)
    parser.add_argument('--box', type=float, nargs=4, required=True)
    parser.add_argument('--output', type=Path, default=Path('tmp/land-overlay.png'))
    args = parser.parse_args()
    base = args.base.rstrip('/') + '/huiyan/land/'
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPCookieProcessor(jar))

    def request(path='', data=None, kind='application/json'):
        headers = {'Content-Type': kind}
        if data is not None:
            headers['X-CSRFToken'] = next(c.value for c in jar if c.name == 'csrftoken')
        return opener.open(urllib.request.Request(base + path, data=data, headers=headers), timeout=180)

    def api(action, payload=None):
        body = json.dumps({'action': action, **(payload or {})}).encode()
        return json.load(request('workbench/api/' + action, body))

    request().close()
    request('workbench/').close()  # Lazily start the configured local service.
    try:
        print('upload', request('workbench/upload', args.image.read_bytes(), 'image/jpeg').status)
        status = json.load(request('workbench/api/status'))
        print('image', json.dumps({k: status.get(k) for k in ('has_image', 'w', 'h', 'model', 'device')}))
        result = api('predict', {'box': args.box})
        status = json.load(request('workbench/api/status'))
        objects = status['objects']
        assert objects and objects[-1]['score'] > 0 and objects[-1]['has_mask'], (result, objects)
        obj_id = objects[-1]['id']
        print('mask', json.dumps({k: objects[-1].get(k) for k in ('id', 'score', 'bbox', 'area')}))
        api('rename', {'obj_id': obj_id, 'name': '测试地物', 'en': 'test feature'})
        api('set_coords', {'obj_id': obj_id, 'lat': 34.75, 'lon': 113.66})
        status = json.load(request('workbench/api/status'))
        obj = next(o for o in status['objects'] if o['id'] == obj_id)
        assert obj['name'] == '测试地物' and obj['en'] == 'test feature'
        print('label_and_coordinates', json.dumps({k: obj.get(k) for k in ('name', 'en', 'lat', 'lon')}, ensure_ascii=True))
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(request('workbench/overlay?a=0.5&hl=' + str(obj_id)).read())
        csv_text = api('export_csv')['csv']
        assert 'test feature' in csv_text and '113.66' in csv_text
        row = next(csv.DictReader(io.StringIO(csv_text.lstrip('\ufeff'))))
        assert float(row['经度']) == 113.66 and float(row['纬度']) == 34.75, row
        print('csv', json.dumps(csv_text[:300], ensure_ascii=True))
        print('overlay', str(args.output), args.output.stat().st_size)
    finally:
        api('clear_objects')
        status = json.load(request('workbench/api/status'))
        print('cleared_objects', len(status['objects']))
        request('release/', b'').close()


if __name__ == '__main__':
    main()
