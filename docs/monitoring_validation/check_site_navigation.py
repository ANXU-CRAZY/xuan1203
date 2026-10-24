import json,re
from pathlib import Path
from playwright.sync_api import sync_playwright
BASE='http://127.0.0.1:8012'
OUT=Path(__file__).resolve().parent
checks=[]
def check(name,ok,detail=None):
    checks.append(dict(name=name,passed=bool(ok),detail=detail))
    print(name,bool(ok),str(detail or '')[:220],flush=True)
    assert ok,name

def ready(page):
    page.wait_for_function("typeof app!=='undefined' && app.serverStats && app.mapMode && !document.querySelector('#thematic-note').textContent.includes('正在')",timeout=60000)

def layout(page):
    return page.evaluate("""() => {
        const r=s=>{const x=document.querySelector(s).getBoundingClientRect();return {left:x.left,right:x.right,top:x.top,bottom:x.bottom,width:x.width,height:x.height}};
        return {width:innerWidth,height:innerHeight,header:r('.top-beam'),filter:r('#filter-bar'),games:r('#games-panel'),overview:r('#detail-panel'),overflow:document.documentElement.scrollWidth>innerWidth};
    }""")

with sync_playwright() as p:
    b=p.chromium.launch(channel='msedge',headless=True)
    ctx=b.new_context(viewport=dict(width=1536,height=850))
    page=ctx.new_page();errors=[];bad=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.on('request',lambda r:bad.append(r.url) if any(x in r.url for x in (':8090','/iserver/','/api/supermap/')) else None)
    page.goto(BASE,wait_until='domcontentloaded');ready(page);page.wait_for_timeout(1000)
    check('lab typeface and palette',page.evaluate("getComputedStyle(document.body).fontFamily.startsWith('Inter') && getComputedStyle(document.body).color==='rgb(23, 43, 53)'"))
    check('brand and institution',page.evaluate("document.querySelector('.brand-title').textContent==='黄河生态方舟' && document.querySelector('.brand-copy small').textContent==='方舟实验室 · 郑州大学地球科学与技术学院 · 郑州市自然保护地事务中心'"))
    check('visit lab destination',page.locator('.lab-visit').get_attribute('href')=='https://3.1415926.love/arklb-geoai/' and page.locator('.lab-visit').get_attribute('rel')=='noopener noreferrer')
    check('six games consolidated',page.locator('#games-panel a').count()==6 and page.locator('#navArea a[href="/bird-guess/"]').count()==0)
    page.locator('#games-toggle').click()
    check('games open',page.locator('#games-panel').is_visible() and page.locator('#games-toggle').get_attribute('aria-expanded')=='true')
    page.screenshot(path=str(OUT/'lab-theme-games.png'))
    page.keyboard.press('Escape');check('escape closes and restores focus',not page.locator('#games-panel').is_visible() and page.evaluate("document.activeElement.id==='games-toggle'"))
    page.locator('#games-toggle').click();page.locator('#games-close').click();check('close button',not page.locator('#games-panel').is_visible())
    page.locator('#games-toggle').click();page.mouse.click(500,320);check('outside click closes',not page.locator('#games-panel').is_visible())
    page.locator('#games-toggle').click();page.keyboard.press('Tab');check('keyboard reaches projects',page.evaluate("document.querySelector('#games-panel').contains(document.activeElement)"));page.keyboard.press('Escape')
    page.evaluate('() => {app.layerControl.expand();}')
    page.locator('.leaflet-control-layers-base label').filter(has_text='不显示底图').hover();page.wait_for_timeout(120)
    page.locator('.leaflet-control-layers-base label').filter(has_text='不显示底图').locator('input').check();page.wait_for_timeout(350)
    check('basemap and annotation stop rendering',page.evaluate("app.map.hasLayer(app.baseLayers.blank) && !app.map.hasLayer(app.baseLayers.vec) && !app.map.hasLayer(app.baseLayers.img) && app.baseLayers.labelLayer.getLayers().length===0"))
    check('data overlays survive basemap off',page.evaluate("app.map.hasLayer(app.layers.record) && app.layers.record.getLayers().length>0 && app.map.hasLayer(app.layers.region) && !!app.heatmap.autoLayer"))
    tile_requests=[]
    page.on('request',lambda r:tile_requests.append(r.url) if 'tianditu.gov.cn' in r.url else None)
    page.evaluate("() => {app.map.panBy([20,0],{animate:false});}");page.wait_for_timeout(650);ready(page)
    check('panning with basemap off does not request tiles',not tile_requests)
    page.screenshot(path=str(OUT/'lab-theme-basemap-off.png'))
    page.evaluate('() => {app.layerControl.expand();}')
    page.locator('.leaflet-control-layers-base label').filter(has_text='卫星影像').hover();page.wait_for_timeout(120)
    page.locator('.leaflet-control-layers-base label').filter(has_text='卫星影像').locator('input').check()
    check('satellite and labels restore',page.evaluate("app.map.hasLayer(app.baseLayers.img) && app.baseLayers.labelLayer.getLayers().length===1 && app.baseLayers.labelLayer.getLayers()[0]._url.includes('cia_w')"))
    page.evaluate('() => {app.layerControl.expand();}')
    page.locator('.leaflet-control-layers-base label').filter(has_text='电子地图').hover();page.wait_for_timeout(120)
    page.locator('.leaflet-control-layers-base label').filter(has_text='电子地图').locator('input').check()
    check('electronic basemap restores',page.evaluate("app.map.hasLayer(app.baseLayers.vec) && app.baseLayers.labelLayer.getLayers()[0]._url.includes('cva_w')"))
    check('heat above points preserved',page.evaluate("Number(getComputedStyle(app.map.getPane('heatmapPane')).zIndex)>Number(getComputedStyle(app.map.getPane('recordPane')).zIndex)"))
    # Responsive header, popup and overview positioning.
    for w,h in [(1536,850),(1280,720),(1024,768),(768,1024),(390,844)]:
        page.set_viewport_size(dict(width=w,height=h));page.wait_for_timeout(550)
        page.locator('#games-toggle').click();g=layout(page)
        check(str(w)+' header and games fit',not g['overflow'] and g['games']['left']>=0 and g['games']['right']<=w and g['games']['top']>=g['header']['bottom'] and g['games']['bottom']<=h,g)
        page.screenshot(path=str(OUT/('lab-theme-'+str(w)+'-games.png')))
        page.keyboard.press('Escape')
        check(str(w)+' toolbar below header',layout(page)['filter']['top']>=layout(page)['header']['bottom'])
        if w>1024:check(str(w)+' overview stays lower right',abs(layout(page)['overview']['bottom']-(h-20))<1)
    check('monitor no JS errors or forbidden requests',not errors and not bad,dict(errors=errors,forbidden=bad))
    # Authenticated navigation is checked without changing local accounts.
    user_ctx=b.new_context(viewport=dict(width=1536,height=850))
    user_ctx.add_init_script("localStorage.setItem('yb_token','local-navigation-test');localStorage.setItem('yb_user',JSON.stringify({username:'测试用户',score:23}));")
    user_ctx.route('**/api/profiles/me/',lambda route:route.fulfill(status=200,content_type='application/json',body=json.dumps(dict(username='测试用户',score=23))))
    user_page=user_ctx.new_page();user_page.goto(BASE,wait_until='domcontentloaded');ready(user_page)
    check('signed-in profile and game access',user_page.locator('#navUser').is_visible() and not user_page.locator('#navGuest').is_visible() and user_page.locator('#navScore span').inner_text()=='23')
    user_page.locator('#games-toggle').click();check('signed-in games open',user_page.locator('#games-panel').is_visible());user_ctx.close()
    routes=['/species/','/articles/','/gallery/','/image-gallery/','/login/','/report/','/profile/','/bird-guess/','/bird-runner/','/wetland-restorer/','/migration/','/wetland-detective/','/floating-island/']
    for route in routes:
        response=ctx.request.get(BASE+route)
        html=response.text()
        check(route+' public theme renders',response.status==200 and 'site-theme.css?v=20261024-3' in html and 'data-ark-page=' in html)
    for route in ['/species/','/articles/','/gallery/','/login/']:
        sub=ctx.new_page();sub.goto(BASE+route,wait_until='domcontentloaded');sub.wait_for_timeout(450)
        check(route+' actual computed theme',sub.evaluate("getComputedStyle(document.body).fontFamily.startsWith('Inter') && getComputedStyle(document.body).backgroundColor==='rgb(247, 249, 247)'"))
        sub.screenshot(path=str(OUT/('lab-theme-'+route.strip('/')+'.png')));sub.close()
    b.close()
(OUT/'site-navigation-results.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2),encoding='utf-8')
