"""Real browser interaction checks for the local infrastructure overlays."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

OUT=Path(__file__).resolve().parent
checks=[]


def check(name,condition,detail=None):
    checks.append(dict(name=name,passed=bool(condition),detail=detail))
    print(name,'PASS' if condition else 'FAIL',str(detail or '')[:160],flush=True)
    assert condition,name


with sync_playwright() as p:
    browser=p.chromium.launch(channel='msedge',headless=True,args=['--no-proxy-server'])
    page=browser.new_page(viewport={'width':1536,'height':960})
    errors,bad,requests=[],[],[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.on('response',lambda r:bad.append([r.status,r.url]) if 'monitoring-tower' in r.url and r.status>=400 else None)
    page.on('request',lambda r:requests.append(r.url))
    try:
        response=page.goto('http://127.0.0.1:8012/',wait_until='domcontentloaded',timeout=60000)
        page.wait_for_function('typeof app!=="undefined" && app.monitoringTowersLoaded',timeout=60000)
        check('图层菜单默认收起',page.evaluate('!app.layerControl.getContainer().classList.contains("leaflet-control-layers-expanded")'))
        counts=page.evaluate('({existing:app.layers.monitoringTowers.getLayers().length,planned:app.layers.plannedMonitoringTowers.getLayers().length,visible:app.map.hasLayer(app.layers.monitoringTowers)&&app.map.hasLayer(app.layers.plannedMonitoringTowers)})')
        check('首页与两个默认图层',response.status==200 and counts==dict(existing=22,planned=29,visible=True),counts)
        check('图层仅显示名称',page.locator('[data-tower-layer="existing"]').inner_text().strip()=='监控塔点位' and page.locator('[data-tower-layer="planned"]').inner_text().strip()=='拟新建监控塔点位')
        page.wait_for_function('app.serverStats && app.mapClusters.length>0',timeout=60000)
        page.wait_for_timeout(700)
        page.screenshot(path=str(OUT/'monitoring-towers-desktop.png'))
        # Show the actual point by geographic location; click the rendered DOM icon.
        page.evaluate('void app.map.setView(app.monitoringTowerMarkers[0].getLatLng(),14,{animate:false})')
        page.wait_for_timeout(500)
        first=page.locator('.monitoring-tower-marker:not(.is-planned)').first
        first.click(position={'x':17,'y':18})
        page.wait_for_timeout(400)
        check('塔位点击弹窗与高亮',page.locator('.monitoring-tower-popup').is_visible() and page.evaluate('!!app._selectedMonitoringTower && app.hitLayer.getLayers().length===1'))
        popup_text=page.locator('.monitoring-tower-popup').inner_text()
        check('弹窗只显示名称与类别',all(x in popup_text for x in ('俩沟村','监控塔点位')) and not any(x in popup_text for x in ('经度','纬度','来源','112.8289383','34.8084916')))
        check('放大后名称横排并避让',page.evaluate('app.monitoringTowerMarkers.some(m=>m.getTooltip().options.permanent) && [...document.querySelectorAll(".monitoring-tower-tooltip")].every(el=>getComputedStyle(el).whiteSpace==="nowrap" && el.getBoundingClientRect().height<32)'))
        page.screenshot(path=str(OUT/'monitoring-tower-detail.png'))
        page.locator('.monitoring-tower-popup .leaflet-popup-close-button').click()
        check('关闭清除选中',page.evaluate('!app._selectedMonitoringTower && app.hitLayer.getLayers().length===0'))
        first.click(position={'x':17,'y':18})
        page.keyboard.press('Escape')
        check('再次打开和 ESC 关闭',page.evaluate('!app._selectedMonitoringTower && !app.map._popup?.isOpen()'))
        first.focus()
        first.press('Enter')
        check('键盘 Enter 打开塔位',page.locator('.monitoring-tower-popup').last.is_visible() and page.evaluate('!!app._selectedMonitoringTower?.popup.isOpen()'))
        page.keyboard.press('Escape')
        # A real layer-control checkbox removes/re-adds the complete 29-point layer.
        page.locator('.leaflet-control-layers-toggle').click()
        planned=page.locator('.leaflet-control-layers label').filter(has=page.locator('[data-tower-layer="planned"]'))
        # Leaflet temporarily suppresses clicks in the same event turn as
        # mouse-enter expansion; let that normal control guard settle.
        planned.hover()
        page.wait_for_timeout(150)
        planned.locator('input').click()
        page.wait_for_timeout(100)
        check('拟新建图层关闭',page.evaluate('!app.map.hasLayer(app.layers.plannedMonitoringTowers)'))
        planned.locator('input').click()
        page.wait_for_timeout(100)
        check('拟新建图层恢复不重复',page.evaluate('app.map.hasLayer(app.layers.plannedMonitoringTowers) && app.layers.plannedMonitoringTowers.getLayers().length===29'))
        # Include the extended attachment-bearing point that a fixed-offset parser loses.
        page.evaluate('''() => {
            app.map.setView(app.monitoringTowerMarkers.find(m=>m.feature.properties.name.includes("飞龙顶")).getLatLng(),14,{animate:false});
        }''')
        page.wait_for_timeout(350)
        page.locator('.monitoring-tower-marker[title="飞龙顶拟建监控塔 26"]').click(position={'x':17,'y':18})
        check('扩展格式点位名称', '飞龙顶拟建监控塔 26' in page.locator('.monitoring-tower-popup').inner_text())
        page.keyboard.press('Escape')
        page.evaluate('app.toggleHeatSelection(true)')
        point=page.evaluate('app.map.latLngToContainerPoint(app.monitoringTowerMarkers.find(m=>m.feature.properties.name.includes("飞龙顶")).getLatLng())')
        page.mouse.click(point['x'],point['y'])
        check('热力圈选优先，不打开塔详情',page.evaluate('!app._selectedMonitoringTower && !app.map._popup?.isOpen()'))
        page.evaluate('app.toggleHeatSelection(false);app.toggleBufferAnalysis(true);app.pickBufferCenter()')
        page.mouse.click(point['x'],point['y'])
        check('缓冲可选择塔位为中心',page.evaluate('!app.bufferAnalysis.picking && !!app.bufferAnalysis.center && !app._selectedMonitoringTower'),page.evaluate('app.bufferAnalysis.center'))
        page.evaluate('app.toggleBufferAnalysis(false)')
        # Existing observation modal remains usable after selecting infrastructure.
        page.evaluate('void app.map.setView([34.76886,113.58632],14,{animate:false})')
        page.wait_for_function('Object.values(app.recordMarkers).length>0',timeout=60000)
        page.evaluate('void Object.values(app.recordMarkers)[0].fire("click")')
        page.wait_for_function('document.querySelector("#detail-modal-overlay").classList.contains("active")',timeout=60000)
        check('原观鸟详情与高亮',page.evaluate('app.hitLayer.getLayers().length===1 && !app._selectedMonitoringTower'))
        page.keyboard.press('Escape')
        page.evaluate('app.setProtectionFilter("国家一级");void app.map.setZoom(10,{animate:false})')
        page.wait_for_timeout(300)
        check('筛选缩放保留全部塔位且无聚合',page.evaluate('app.layers.monitoringTowers.getLayers().length===22 && app.layers.plannedMonitoringTowers.getLayers().length===29 && app.monitoringTowerMarkers.every(m=>!m.getTooltip().options.permanent)'))
        # Mobile popup is within the viewport and the two controls remain available.
        page.close()
        page=browser.new_page(viewport={'width':390,'height':844},has_touch=True,is_mobile=True)
        page.on('pageerror',lambda e:errors.append(str(e)))
        page.on('response',lambda r:bad.append([r.status,r.url]) if 'monitoring-tower' in r.url and r.status>=400 else None)
        page.on('request',lambda r:requests.append(r.url))
        page.goto('http://127.0.0.1:8012/',wait_until='domcontentloaded')
        page.wait_for_function('app.monitoringTowersLoaded && app.serverStats && app._hasInitialView',timeout=60000)
        page.evaluate('app.map.invalidateSize();void app.map.setView(app.monitoringTowerMarkers[0].getLatLng(),14,{animate:false})')
        page.wait_for_timeout(500)
        page.locator('.monitoring-tower-marker:not(.is-planned)').first.click(position={'x':17,'y':18})
        page.wait_for_timeout(400)
        box=page.locator('.monitoring-tower-popup').bounding_box()
        check('手机弹窗无横向溢出',box and box['x']>=0 and box['x']+box['width']<=390,box)
        filter_bottom=page.locator('#filter-bar').bounding_box()
        check('手机弹窗避让筛选栏',box['y']>=filter_bottom['y']+filter_bottom['height'])
        page.screenshot(path=str(OUT/'monitoring-tower-mobile.png'))
        page.keyboard.press('Escape')
        page.locator('.leaflet-control-layers-toggle').tap()
        check('手机图层菜单保留两个开关',page.locator('[data-tower-layer="existing"]').is_visible() and page.locator('[data-tower-layer="planned"]').is_visible())
        check('无新增浏览器错误与资源失败',not errors and not bad,dict(errors=errors,bad=bad))
        check('无超图请求',not any(any(v in u for v in (':8090','/iserver/','/api/supermap/')) for u in requests))
    finally:
        (OUT/'tower-browser-results.json').write_text(json.dumps({'checks':checks,'errors':errors,'resource_errors':bad},ensure_ascii=False,indent=2),encoding='utf8')
        browser.close()
