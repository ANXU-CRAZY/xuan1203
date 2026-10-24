"""Real-browser checks against a running original Django dashboard.

Usage: anxu\Scripts\python.exe docs\monitoring_validation\browser_check.py
Uses its own headless Edge instance; never touches other project services.
"""
import csv
import io
import json
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path(__file__).resolve().parent
BASE = 'http://127.0.0.1:8012'
checks = []


def check(name, condition, detail=None):
    checks.append({'name': name, 'passed': bool(condition), 'detail': detail})
    print(name, 'PASS' if condition else 'FAIL', str(detail or '')[:200], flush=True)
    assert condition, name


def ready(page):
    page.wait_for_function("typeof app !== 'undefined' && app.serverStats && app.timeline.years.length && app.mapClusters.length && !document.querySelector('#thematic-note').textContent.includes('正在')", timeout=60000)


def wait_map(page):
    page.wait_for_function("!document.querySelector('#thematic-note').textContent.includes('正在')", timeout=60000)


def layout(page, name):
    page.screenshot(path=str(OUT / f'{name}.png'), full_page=True)
    result = page.evaluate('''() => {
        const r = id => document.getElementById(id).getBoundingClientRect();
        const intersect = (a,b) => a.width && a.height && b.width && b.height && a.left<b.right && a.right>b.left && a.top<b.bottom && a.bottom>b.top;
        const panel = r('analysis-panel'), filter = r('filter-bar'), bottom = document.querySelector('.bottom-stats-bar').getBoundingClientRect();
        const layers = document.querySelector('.leaflet-control-layers').getBoundingClientRect();
        return {overflow:document.documentElement.scrollWidth>innerWidth, filterOverlap:intersect(panel,filter), bottomOverlap:intersect(panel,bottom), layerOverlap:intersect(panel,layers), panel:{top:panel.top,bottom:panel.bottom,left:panel.left,right:panel.right}, sidebarBottom:r('monitor-sidebar').bottom};
    }''')
    check(name + ' 布局', not any(result[k] for k in ('overflow','filterOverlap','bottomOverlap','layerOverlap')), result)


with sync_playwright() as p:
    browser = p.chromium.launch(channel='msedge', headless=True)
    context = browser.new_context(viewport={'width':1440,'height':900}, accept_downloads=True)
    page = context.new_page()
    errors, bad_requests, requests, api_errors = [], [], [], []
    page.on('pageerror', lambda e: errors.append(str(e)))
    page.on('request', lambda r: (requests.append(r.url), bad_requests.append(r.url) if any(x in r.url for x in (':8090','/iserver/','/api/supermap/')) else None))
    page.on('response', lambda r: api_errors.append([r.status,r.url]) if r.url.startswith(BASE+'/api/') and r.status>=400 else None)
    page.goto(BASE, wait_until='domcontentloaded', timeout=60000)
    ready(page)
    check('真实年份', page.evaluate('app.timeline.years') == list(range(2014,2025)))
    check('默认观鸟图层和天地图', page.evaluate("app.map.hasLayer(app.layers.record) && Object.values(app.map._layers).some(l=>l._url?.includes('tianditu'))"))
    page.evaluate('() => {app.map.removeLayer(app.layers.record);}')
    check('观鸟图层开关同步图例',not page.locator('#thematic-legend').is_visible())
    page.evaluate('() => {app.layers.record.addTo(app.map);}')
    page.screenshot(path=str(OUT/'desktop-initial.png'))

    # Actual cluster marker event -> zoom -> bounded true point page.
    page.evaluate("() => {app.layers.record.getLayers()[0].fire('click');}")
    page.wait_for_function("app.mapMode==='points'", timeout=60000)
    wait_map(page)
    check('聚合点缩放展开', page.evaluate("app.map.getZoom()>=14 && app.pointPage.length>0 && app.pointPage.length<=5000"))
    page.evaluate("() => {app.map.setView([34.76886,113.58632],14,{animate:false});}")
    wait_map(page); page.wait_for_timeout(300); wait_map(page)
    check('密集区真实点非空', page.evaluate('app.pointPage.length>0'), page.evaluate('({points:app.pointPage.length,hasMore:!!app.nextPointAfter})'))
    if page.evaluate('Boolean(app.nextPointAfter)'):
        first_ids = page.evaluate('app.pointPage.map(r=>r.id)')
        page.locator('#point-next').click(); wait_map(page)
        second_ids = page.evaluate('app.pointPage.map(r=>r.id)')
        check('受控下一页不重复且保留概览', not set(first_ids)&set(second_ids) and page.evaluate('app.layers.record.getLayers().length>app.pointPage.length'))
    page.evaluate("() => {app.map.panBy([80,40],{animate:false});}")
    page.wait_for_timeout(300); wait_map(page)
    check('平移视域更新', page.evaluate('app.pointPage.length>0'))

    # Keep the original complete modal, adding a selected-point highlight.
    page.evaluate('() => {Object.values(app.recordMarkers)[0].fire("click");}')
    page.locator('#detail-modal-overlay.active').wait_for(timeout=30000)
    check('点选完整详情及高亮', page.evaluate('app.hitLayer.getLayers().length===1 && !!app.charts.modalLevel && !!app.charts.modalZone'))
    page.screenshot(path=str(OUT/'desktop-detail.png'))
    page.keyboard.press('Escape')
    check('关闭详情清除高亮', page.evaluate('app.hitLayer.getLayers().length===0'))

    page.locator('[data-protection-filter="国家一级"]').click(); wait_map(page)
    check('保护等级筛选', page.evaluate("app.pointPage.every(r=>app.getProtectionGroup(r.species_protection)==='国家一级') && app.serverStats.total_records<117911"))
    page.locator('[data-protection-filter="all"]').click(); wait_map(page)
    page.locator('#timeline-year').select_option('2023'); wait_map(page)
    check('年度选择联动', page.evaluate("document.querySelector('#d-start').value==='2023-01-01' && app.pointPage.every(r=>r.observation_time.startsWith('2023')) && app.serverStats.yearly_trend.length===1"))
    page.locator('#timeline-toggle').click()
    page.wait_for_function("document.querySelector('#d-start').value==='2024-01-01' && !app.timeline.playing",timeout=60000)
    wait_map(page)
    check('串行年度播放至结束', page.evaluate("app.pointPage.every(r=>r.observation_time.startsWith('2024')) && app.timeline.timer===null"))
    page.locator('#timeline-year').select_option('2019'); wait_map(page)
    page.locator('#timeline-toggle').click()
    page.locator('#timeline-toggle').click()
    check('年度暂停', page.evaluate('!app.timeline.playing && app.timeline.timer===null'))

    page.locator('#monitor-tools-toggle').click()
    page.locator('#d-start').fill('2014-01-01'); page.locator('#d-end').fill('2024-12-31')
    page.locator('.btn-go').click(); wait_map(page)
    page.locator('#buffer-analysis-toggle').click()
    layout(page,'desktop-tools')
    # Click on map, away from panels; then use exact dense data coordinate.
    point=page.evaluate("() => {const p=app.map.latLngToContainerPoint([34.76886,113.58632]);return {x:p.x,y:p.y};}")
    page.locator('#map').click(position=point)
    check('地图点击选缓冲中心', page.evaluate('!!app.bufferAnalysis.center && !app.bufferAnalysis.picking'))
    page.evaluate("() => {app.pickBufferCenter(); app.map.fire('click',{latlng:L.latLng(34.76886,113.58632)});}")
    page.locator('#analysis-run').click()
    page.wait_for_function('app.bufferAnalysis.payload!==null',timeout=60000)
    summary=page.evaluate('app.bufferAnalysis.payload.summary')
    check('500 米缓冲与完整统计', summary['total_records']>0 and summary['bird_count']>=summary['total_records'],summary)
    check('缓冲范围显示',page.evaluate('app.bufferAnalysis.layer.getLayers().length>1'))
    page.locator('#analysis-results button').first.click()
    page.locator('#detail-modal-overlay.active').wait_for(timeout=30000)
    check('缓冲记录详情',page.evaluate('app.hitLayer.getLayers().length===1'))
    page.keyboard.press('Escape')
    with page.expect_download(timeout=60000) as download:
        page.locator('#analysis-export').click()
    target=OUT/'buffer-all-records.csv'
    download.value.save_as(target)
    raw=target.read_bytes()
    rows=list(csv.reader(io.StringIO(raw.decode('utf-8-sig'))))
    check('CSV 全量与 UTF-8 BOM',raw.startswith(b'\xef\xbb\xbf') and len(rows)-1==summary['total_records'],{'rows':len(rows)-1})
    page.locator('#analysis-clear').click()
    check('清除分析',page.evaluate('app.bufferAnalysis.center===null && app.bufferAnalysis.layer.getLayers().length===0 && document.querySelector("#analysis-export").disabled'))
    page.locator('#analysis-panel .panel-head button').click()
    check('关闭分析',not page.locator('#analysis-panel').is_visible())
    page.locator('#buffer-analysis-toggle').click()
    check('重开分析等待新中心',page.evaluate('app.bufferAnalysis.active && app.bufferAnalysis.picking && app.bufferAnalysis.payload===null'))
    page.evaluate("() => {app.map.fire('click',{latlng:L.latLng(34.81704478,112.85377264)});}")
    page.locator('#analysis-run').click()
    page.wait_for_function('app.bufferAnalysis.payload!==null',timeout=60000)
    check('原版有效样线查询',page.evaluate('app.bufferAnalysis.payload.summary.matched_routes>0'),page.evaluate('app.bufferAnalysis.payload.summary'))
    page.locator('#analysis-panel .panel-head button').click()

    # Heat selection uses all filtered records, not the current point page.
    page.locator('#heat-toggle').click()
    page.mouse.move(600,300); page.mouse.down(); page.mouse.move(900,600,steps=6); page.mouse.up()
    page.wait_for_function("document.querySelector('#heat-info-text').textContent.includes('圈选完整统计')",timeout=60000)
    check('热力圈选完整统计',page.evaluate('!!app.heatmap.layer && !!app.heatmap.bounds'))
    page.locator('.btn-clear[title="清除热力圈选"]').click()
    check('清除热力圈选',page.evaluate('app.heatmap.bounds===null && app.heatmap.layer===null'))

    for width,height,name in [(1280,720,'laptop-tools'),(820,1180,'tablet-tools'),(390,844,'mobile-tools'),(375,667,'small-mobile-tools')]:
        page.set_viewport_size({'width':width,'height':height})
        page.evaluate('app.toggleBufferAnalysis(true);app.layoutMonitoring()')
        page.wait_for_timeout(400)
        layout(page,name)
        page.evaluate('app.toggleBufferAnalysis(false)')

    # Simulate unavailable brand artwork; a Chinese fallback remains visible.
    page.evaluate("document.querySelector('.brand-logo').dispatchEvent(new Event('error'))")
    check('Logo 加载兜底',page.locator('.brand-logo-fallback').is_visible())
    # Deliberately ignore cancellation on an old request and delay its response.
    # The sequence/filter guard must still protect the newer data.
    page.evaluate('''() => {
        app.toggleMonitoringTools(false);
        window.savedFetch=window.fetch;
        window.fetch=(url,options={}) => {
            if(String(url).includes('/api/map-observations/') && String(url).includes('start=2014-01-01')) {
                const opts={...options};delete opts.signal;
                return savedFetch(url,opts).then(response=>new Promise(resolve=>setTimeout(()=>resolve(response),1800)));
            }
            return savedFetch(url,options);
        };
        document.querySelector('#d-start').value='2014-01-01';document.querySelector('#d-end').value='2014-12-31';
        app.loadMapObservations();
        document.querySelector('#d-start').value='2024-01-01';document.querySelector('#d-end').value='2024-12-31';
        app.loadMapObservations();
    }''')
    wait_map(page);page.wait_for_timeout(3500)
    check('旧响应不能覆盖新年度',page.evaluate("app.serverStats.yearly_trend.every(y=>y.year===2024) && document.querySelector('#d-start').value==='2024-01-01'"))
    page.evaluate('window.fetch=window.savedFetch')
    # Synthetic year metadata is confined to these explicit edge-case tests.
    page.route('**/api/monitoring/years/**',lambda route:route.fulfill(json={'years':[]}))
    page.evaluate('async()=>{await app.loadMonitoringYears();}')
    check('空年份禁用播放',page.locator('#timeline-toggle').is_disabled())
    page.unroute('**/api/monitoring/years/**')
    page.route('**/api/monitoring/years/**',lambda route:route.fulfill(json={'years':[2024]}))
    page.evaluate('async()=>{await app.loadMonitoringYears();await app.toggleTimeline();}')
    check('单年份播放后停止',page.evaluate('!app.timeline.playing && app.timeline.timer===null'))
    page.unroute('**/api/monitoring/years/**')
    check('无新增 JavaScript 异常',not errors,errors)
    check('无超图依赖请求',not bad_requests,bad_requests)
    check('无接口错误响应',not api_errors,api_errors)
    (OUT/'browser-results.json').write_text(json.dumps({'checks':checks,'page_errors':errors,'api_errors':api_errors,'forbidden_requests':bad_requests,'api_request_count':sum('/api/' in u for u in requests)},ensure_ascii=False,indent=2),encoding='utf-8')
    context.close(); browser.close()
