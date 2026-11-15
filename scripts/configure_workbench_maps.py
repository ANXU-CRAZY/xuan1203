"""Read existing local map keys without printing them or adding them to Git."""
import argparse
import ast
import json
from pathlib import Path
import re


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--amap-notebook', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    html = (root / 'app_monitor/templates/index.html').read_text(encoding='utf-8')
    section = html[html.index('initMap: function()'):]
    match = re.search(r'const\s+tk\s*=\s*["\']([^"\']+)', section)
    if not match:
        raise SystemExit('The existing platform Tianditu configuration was not found.')
    notebook = json.loads(args.amap_notebook.read_text(encoding='utf-8-sig'))
    amap = None
    for cell in notebook.get('cells', []):
        if cell.get('cell_type') != 'code':
            continue
        try:
            tree = ast.parse(''.join(cell.get('source', [])))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if (isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant)
                    and isinstance(node.value.value, str)
                    and any(isinstance(t, ast.Name) and t.id.upper() in ('KEY', 'AMAP_KEY', 'GAODE_KEY') for t in node.targets)
                    and re.fullmatch(r'[a-zA-Z0-9]{20,64}', node.value.value)):
                amap = node.value.value
    if not amap:
        raise SystemExit('An AMap Web Service key was not found in the specified notebook.')
    target = root / 'var/geolibre/providers.json'
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({'tianditu_key': match[1], 'amap_key': amap, 'amap_kind': 'webservice'}), encoding='utf-8')
    print('Local map provider configuration updated. Keys were not printed.')


if __name__ == '__main__':
    main()
