import json
from pathlib import Path
from playwright.sync_api import sync_playwright
OUT=Path(__file__).resolve().parent
BASE='http://127.0.0.1:8012'
results=[]
def check(name, ok, detail=None):
    print(name, bool(ok), str(detail or '')[:450], flush=True)
    results.append(dict(name=name, passed=bool(ok), detail=detail))
    assert ok, name

def ready(page):
    page.wait_for_function("typeof app!=='undefined' && app.serverStats && app.mapMode && !document.querySelector('#thematic-note').textContent.includes('正在')",timeout=60000)
    page.wait_for_timeout(450)

def geometry(page):
    return page.evaluate("""() => {
      const r=id=>{const x=document.getElementById(id).getBoundingClientRect();return {x:x.x,y:x.y,w:x.width,h:x.height,right:x.right,bottom:x.bottom}};
      return {width:innerWidth,height:innerHeight,bar:r('filter-bar'),detail:r('detail-panel'),panel:r('analysis-panel'),bottom:document.querySelector('.bottom-stats-bar').getBoundingClientRect().toJSON(),overflow:document.documentElement.scrollWidth>innerWidth};
    }""")

with sync_playwright() as p:
    b=p.chromium.launch(channel='msedge',headless=True)
    errors=[]; forbidden=[]; api_errors=[]
    page=b.new_page(viewport=dict(width=1536,height=800),accept_downloads=True)
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.on('request',lambda r:forbidden.append(r.url) if any(t in r.url for t in (':8090','/iserver/','/api/supermap/')) else None)
    page.on('response',lambda r:api_errors.append([r.status,r.url]) if r.url.startswith(BASE+'/api/') and r.status>=400 else None)
    page.goto(BASE,wait_until='domcontentloaded');ready(page)
    page.wait_for_timeout(1500);ready(page)
    check('static version actually served',page.locator('link[href*="monitoring.css"]').get_attribute('href').endswith('20261024-4'))
    g=geometry(page)
    check('overview bottom right',abs(g['detail']['bottom']-(g['height']-20))<1 and abs(g['detail']['right']-(g['width']-20))<1,g)
    check('toolbar original compact proportions',990<g['bar']['w']<1030 and g['bar']['x']>450 and g['bar']['h']<60,g['bar'])
    counts=page.evaluate("({zoom:app.map.getZoom(),symbols:app.mapClusters.length,locations:new Set(app.mapClusters.map(x=>x.lng+','+x.lat)).size,records:app.mapClusters.reduce((n,x)=>n+x.cluster_size,0),birds:app.mapClusters.reduce((n,x)=>n+x.count,0),stats:app.serverStats.total_records})")
    check('all distinct sites and all records represented',counts['locations']==1124 and counts['records']==117911 and counts['birds']==1216810,counts)
    check('original circle markers and thematic card removed',page.evaluate("app.layers.record.getLayers().every(l=>l instanceof L.CircleMarker && l.options.radius===6) && getComputedStyle(document.querySelector('#thematic-legend')).display==='none'"))
    page.screenshot(path=str(OUT/'corrected-desktop.png'))
    # Real repeated-site symbol click then high-zoom query, preserving the complete footprint.
    page.evaluate("() => { app.layers.record.getLayers()[app.mapClusters.findIndex(x=>x.cluster_size>1)].fire('click'); }");page.wait_for_timeout(450);ready(page)
    check('cluster expands',page.evaluate('app.map.getZoom()>8.25'))
    page.evaluate("() => { app.map.setView([34.76886,113.58632],14,{animate:false}); }");page.wait_for_timeout(500);ready(page)
    check('dense area bounded details and paging',page.evaluate("app.pointPage.length===5000 && app.nextPointAfter && !document.querySelector('#point-pagination').hidden && app.layers.record.getLayers().length>5000"))
    ids=page.evaluate('app.pointPage.map(r=>r.id)')
    page.locator('#point-next').click();ready(page)
    ids2=page.evaluate('app.pointPage.map(r=>r.id)')
    check('next page reachable and distinct',len(ids2)<=5000 and not (set(ids)&set(ids2)))
    page.evaluate("() => { Object.values(app.recordMarkers)[0].fire('click'); }")
    page.locator('#detail-modal-overlay.active').wait_for()
    check('record details and highlight',page.evaluate('app.hitLayer.getLayers().length===1 && !!app.charts.modalLevel'))
    page.keyboard.press('Escape')
    page.locator('[data-protection-filter="国家一级"]').click();ready(page)
    check('protection filter',page.evaluate("app.pointPage.every(r=>app.getProtectionGroup(r.species_protection)==='国家一级')"))
    page.locator('[data-protection-filter="all"]').click();ready(page)
    page.locator('#timeline-toggle').click();page.wait_for_timeout(100)
    check('play icon toggles',page.evaluate("app.timeline.playing && document.querySelector('#timeline-toggle i').classList.contains('fa-pause')"))
    page.locator('#timeline-toggle').click()
    check('playback pauses',page.evaluate('!app.timeline.playing && app.timeline.timer===null'))
    page.locator('#d-start').fill('2014-01-01');page.locator('#d-end').fill('2024-12-31');page.locator('.btn-go').click();ready(page)
    page.locator('#buffer-analysis-toggle').click()
    page.evaluate("() => { app.map.fire('click',{latlng:L.latLng(34.76886,113.58632)}); }")
    page.locator('#analysis-run').click();page.wait_for_function('app.bufferAnalysis.payload!==null',timeout=60000)
    summary=page.evaluate('app.bufferAnalysis.payload.summary')
    check('500m analysis unchanged',summary['total_records']==5179 and summary['bird_count']==33027 and summary['species_count']==142,summary)
    with page.expect_download() as download:page.locator('#analysis-export').click()
    download.value.save_as(str(OUT/'recheck-buffer.csv'))
    import csv,io
    raw=(OUT/'recheck-buffer.csv').read_bytes()
    check('CSV all records',raw.startswith(b'\xef\xbb\xbf') and len(list(csv.reader(io.StringIO(raw.decode('utf-8-sig')))))-1==5179)
    page.locator('#analysis-clear').click();check('analysis clear',page.evaluate('app.bufferAnalysis.center===null'))
    page.locator('#analysis-panel .panel-head button').click()
    check('overview restores bottom right after closing',page.locator('#detail-panel').is_visible() and abs(geometry(page)['detail']['bottom']-780)<1)
    page.locator('#buffer-analysis-toggle').click();check('analysis reopens',page.locator('#analysis-panel').is_visible())
    page.locator('#analysis-panel .panel-head button').click()
    for width,height in [(1440,900),(1280,720),(1024,768),(768,1024),(390,844)]:
        page.set_viewport_size(dict(width=width,height=height));page.wait_for_timeout(550);ready(page)
        check(str(width)+' no document overflow',not geometry(page)['overflow'],geometry(page))
        if width>768:
            g=geometry(page);check(str(width)+' overview lower right',g['detail']['right']<=width-12 and g['detail']['bottom']>=height-100 and g['detail']['y']>g['bar']['bottom'])
        page.locator('#buffer-analysis-toggle').click();page.wait_for_timeout(120)
        g=geometry(page)
        check(str(width)+' analysis within available map',g['panel']['y']>=g['bar']['bottom'] and g['panel']['bottom']<=g['bottom']['top'],g)
        page.screenshot(path=str(OUT/('corrected-'+str(width)+'.png')))
        page.locator('#analysis-panel .panel-head button').click()
    check('no JS/API errors or forbidden dependencies',not errors and not api_errors and not forbidden,dict(js=errors,api=api_errors,forbidden=forbidden))
    b.close()
(OUT/'display-recheck-results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
