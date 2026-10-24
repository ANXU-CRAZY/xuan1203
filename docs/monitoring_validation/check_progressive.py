import json, os
from pathlib import Path
from playwright.sync_api import sync_playwright
BASE=os.environ.get('MONITOR_BASE','http://127.0.0.1:8012')
results=[]
EXPECTED = json.loads(Path(os.environ['MONITOR_EXPECTED_JSON']).read_text()) if os.environ.get('MONITOR_EXPECTED_JSON') else {'records':117911,'birds':1216810,'locations':1124,'dense_center':[113.58632,34.76886],'years':list(range(2014,2025)),'buffer_500':{'total_records':5179,'bird_count':33027,'species_count':142}}

def check(name,ok,detail=None):
 results.append(dict(name=name,passed=bool(ok),detail=detail)); print(name,bool(ok),str(detail or '')[:200],flush=True); assert ok,name
with sync_playwright() as p:
 browser=p.chromium.launch(channel='msedge',headless=True)
 page=browser.new_page(viewport={'width':1536,'height':850})
 errors=[]; requests=[]
 page.on('pageerror',lambda e:errors.append(str(e)))
 page.on('request',lambda r:requests.append(r.url))
 page.goto(BASE,wait_until='domcontentloaded')
 page.wait_for_function('typeof app!=="undefined" && app._completeMapLoaded && app.serverStats',timeout=90000)
 page.wait_for_timeout(500)
 check('preview and complete requested',any('stage=preview' in u for u in requests) and any('/api/map-observations/' in u and 'stage=' not in u for u in requests))
 held=[]
 def hold_complete(route):
  if 'stage=preview' in route.request.url:route.continue_()
  else:held.append(route)
 page.route('**/api/map-observations/**',hold_complete)
 page.evaluate('() => { app._completeMapLoaded=false; app.loadMapObservations(); }')
 page.wait_for_function('app.pointPage.length>0 && app.pointPage.length<=300 && document.querySelector("#thematic-note").textContent.includes("补全")',timeout=60000)
 page.wait_for_timeout(100)
 check('bounded points painted before full response',page.evaluate('app.layers.record.getLayers().length===app.pointPage.length && app.pointPage.length===300'))
 for route in held:route.fulfill(response=route.fetch(timeout=90000))
 page.wait_for_function('!document.querySelector("#thematic-note").textContent.includes("正在")',timeout=90000)
 page.wait_for_timeout(250)
 counts=page.evaluate('({locations:new Set(app.mapClusters.map(x=>x.lng+","+x.lat)).size,records:app.mapClusters.reduce((n,x)=>n+x.cluster_size,0),stats:app.serverStats.total_records,rendered:app.layers.record.getLayers().length,groups:app.mapClusters.length})')
 check('complete footprint and batched render',counts['locations']==EXPECTED['locations'] and counts['records']==EXPECTED['records'] and counts['rendered']==counts['groups'],counts)
 page.unroute('**/api/map-observations/**',hold_complete)
 def fail_preview(route):
  if 'stage=preview' in route.request.url:route.fulfill(status=503,content_type='application/json',body='{}')
  else:route.continue_()
 page.route('**/api/map-observations/**',fail_preview)
 page.evaluate('() => { app._completeMapLoaded=false; app.loadMapObservations(); }')
 page.wait_for_timeout(100)
 page.wait_for_function('app._completeMapLoaded && !document.querySelector("#thematic-note").textContent.includes("正在")',timeout=90000)
 check('preview failure still completes',page.evaluate('app.mapClusters.reduce((n,x)=>n+x.cluster_size,0)')==EXPECTED['records'])
 page.unroute('**/api/map-observations/**',fail_preview)
 page.evaluate('() => { app.setProtectionFilter("国家一级"); app.setProtectionFilter("国家二级"); }')
 page.wait_for_function('app._statsKey && JSON.parse(app._statsKey)[0]==="国家二级" && !document.querySelector("#thematic-note").textContent.includes("正在")',timeout=90000)
 check('latest filter wins across both stages',page.evaluate('app.mapClusters.every(x=>x.species_protection==="国家二级") && app.protectionFilter==="国家二级"'))
 check('no JS or SuperMap requests',not errors and not any(any(v in u for v in (':8090','/iserver/','/api/supermap/')) for u in requests),errors)
 browser.close()
Path('docs/monitoring_validation/'+os.environ.get('MONITOR_RESULT_PREFIX','')+'progressive-results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
