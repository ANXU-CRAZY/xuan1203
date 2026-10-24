import os
import sys
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()
from django.contrib.gis.geos import GEOSGeometry, Point
from playwright.sync_api import sync_playwright

OUT = Path(__file__).resolve().parent
data = json.loads((ROOT / 'app_monitor/static/app_monitor/geo/protected_areas.geojson').read_text(encoding='utf-8'))
geometries = [GEOSGeometry(json.dumps(f['geometry']), srid=4326) for f in data['features']]
positions = [dict(lng=g.point_on_surface.x, lat=g.point_on_surface.y) for g in geometries]
checks = []


def check(name, ok, detail=None):
    checks.append(dict(name=name, passed=bool(ok), detail=detail))
    print(name, bool(ok), str(detail or '')[:150], flush=True)
    assert ok, name


def ready(page):
    page.wait_for_function("app.mapMode && !document.querySelector('#thematic-note').textContent.includes('正在')", timeout=60000)


with sync_playwright() as p:
    b = p.chromium.launch(channel='msedge', headless=True)
    page = b.new_page(viewport=dict(width=1536, height=850))
    errors = []
    page.on('pageerror', lambda e: errors.append(str(e)))
    page.goto(os.environ.get('MONITOR_BASE', 'http://127.0.0.1:8012')+'/', wait_until='domcontentloaded')
    page.wait_for_function("typeof app!=='undefined' && app.protectedAreaBoundary && app.serverStats", timeout=60000)
    ready(page)
    check('31 valid polygons loaded and all zones default visible', len(geometries) == 31 and all(g.valid for g in geometries) and page.evaluate("['protectedCore','protectedBuffer','protectedExperimental'].every(key=>app.map.hasLayer(app.layers[key])) && app.protectedAreaBoundary.getLayers().length===31"))
    classification = page.evaluate("""() => Object.fromEntries(['protectedCore','protectedBuffer','protectedExperimental'].map(key => {
        const fills=app.layers[key].getLayers()[0].getLayers(), outlines=app.layers[key].getLayers()[1].getLayers();
        return [key,{count:fills.length,nums:[...new Set(fills.map(l=>l.feature.properties.Num))],
                     color:fills[0].options.fillColor,outline:outlines[0].getElement().getAttribute('stroke-dasharray')}];
    }))""")
    check('Num1 core red with dashed outline', classification['protectedCore']['count']==12 and classification['protectedCore']['nums']==[1] and classification['protectedCore']['color']=='#E53935' and classification['protectedCore']['outline']=='6,4',classification['protectedCore'])
    check('Num2 buffer yellow',classification['protectedBuffer']['count']==14 and classification['protectedBuffer']['nums']==[2] and classification['protectedBuffer']['color']=='#FBC02D')
    check('Num3 experimental blue',classification['protectedExperimental']['count']==5 and classification['protectedExperimental']['nums']==[3] and classification['protectedExperimental']['color']=='#2F80ED')
    check('fill below points, outline above heat without intercepting', page.evaluate("Number(getComputedStyle(app.map.getPane('protectedAreaPane')).zIndex)<425 && Number(getComputedStyle(app.map.getPane('protectedAreaOutlinePane')).zIndex)>Number(getComputedStyle(app.map.getPane('heatmapPane')).zIndex) && getComputedStyle(app.map.getPane('protectedAreaOutlinePane')).pointerEvents==='none'"))
    page.screenshot(path=str(OUT / 'protected-area-initial.png'))
    page.evaluate('() => {app.layerControl.expand();}')
    for title,key in [('核心区','protectedCore'),('缓冲区','protectedBuffer'),('实验区','protectedExperimental')]:
        label = page.locator('.leaflet-control-layers-overlays label').filter(has_text=title)
        label.hover(); page.wait_for_timeout(120)
        label.locator('input').uncheck()
        check(title+' fill and outline off independently', page.evaluate("key=>!app.map.hasLayer(app.layers[key]) && app.layers[key].getLayers().every(g=>g.getLayers().every(l=>!app.map.hasLayer(l))) && ['protectedCore','protectedBuffer','protectedExperimental'].filter(k=>k!==key).every(k=>app.map.hasLayer(app.layers[k]))",key))
        label.locator('input').check()
        check(title+' fill and outline restore exactly once', page.evaluate('key=>app.map.hasLayer(app.layers[key]) && app.layers[key].getLayers().length===2',key))
    samples = page.evaluate('app.mapClusters.map(x=>({lng:x.lng,lat:x.lat}))')
    inside = next((s for s in samples if any(g.contains(Point(s['lng'], s['lat'], srid=4326)) for g in geometries)), None)
    check('observation exists inside protected geometry', bool(inside))
    page.evaluate('s=>{app.clearHeatmap();app.map.setView([s.lat,s.lng],14,{animate:false});}', inside)
    page.wait_for_timeout(450)
    ready(page)
    marker = page.evaluate('''()=>{for(const l of Object.values(app.recordMarkers)){const p=app.map.latLngToContainerPoint(l.getLatLng());if(p.x>360&&p.x<1100&&p.y>160&&p.y<650)return {x:p.x,y:p.y};}return null;}''')
    check('true observation page not empty', bool(marker))
    page.mouse.click(marker['x'], marker['y'])
    page.locator('#detail-modal-overlay.active').wait_for(timeout=30000)
    check('observation details retain priority', page.evaluate('app.hitLayer.getLayers().length===1') and not page.locator('.leaflet-popup-content').is_visible())
    page.keyboard.press('Escape')
    page.evaluate('() => {app.map.removeLayer(app.layers.record);app.map.fitBounds(app.protectedAreaBoundary.getBounds().pad(0.12),{animate:false});}')
    page.wait_for_timeout(450)
    pick = page.evaluate('''positions=>{for(const s of positions){const p=app.map.latLngToContainerPoint([s.lat,s.lng]),t=document.elementFromPoint(p.x,p.y);if(p.x>360&&p.x<1100&&p.y>160&&p.y<650&&document.querySelector('#map').contains(t))return {...s,x:p.x,y:p.y};}return null;}''', positions)
    check('protected interior point available', bool(pick), pick)
    page.mouse.click(pick['x'], pick['y'])
    page.locator('.leaflet-popup-content').wait_for()
    text = page.locator('.leaflet-popup-content').inner_text()
    check('protected polygon popup through empty point canvas with correct zone', '保护区范围' in text and any(f['properties']['name'] in text and f['properties']['zone_type'] in text for f in data['features']))
    page.screenshot(path=str(OUT / 'protected-area-detail.png'))
    page.evaluate('() => {app.map.closePopup();}')
    page.locator('.leaflet-popup-content').wait_for(state='hidden')
    page.locator('#buffer-analysis-toggle').click()
    page.mouse.click(pick['x'], pick['y'])
    buffer_state = page.evaluate("({center:app.bufferAnalysis.center,picking:app.bufferAnalysis.picking,active:app.bufferAnalysis.active,body:document.body.className,popup:document.querySelector('.leaflet-popup-content')?.textContent})")
    check('buffer picking passes through polygons', bool(buffer_state['center']) and not buffer_state['picking'] and not page.locator('.leaflet-popup-content').is_visible(), buffer_state)
    page.locator('#analysis-panel .panel-head button').click()
    page.locator('#heat-toggle').click()
    check('heat selection passes through polygons', page.evaluate("getComputedStyle(app.protectedAreaBoundary.getLayers()[0].getElement()).pointerEvents==='none'"))
    page.locator('#heat-toggle').click()
    page.set_viewport_size(dict(width=390, height=844))
    page.wait_for_timeout(250)
    page.evaluate('() => {app.layerControl.expand();}')
    check('mobile layer control available', label.is_visible() and not page.evaluate('document.documentElement.scrollWidth>innerWidth'))
    page.screenshot(path=str(OUT / 'protected-area-mobile.png'))
    check('no JS errors', not errors, errors)
    b.close()
(OUT / (os.environ.get('MONITOR_RESULT_PREFIX','')+'protected-area-results.json')).write_text(json.dumps(checks, ensure_ascii=False, indent=2), encoding='utf-8')
