import os,json,urllib.request,time
from pathlib import Path
from playwright.sync_api import sync_playwright
BASE=os.environ.get('MONITOR_BASE','https://3.1415926.love');checks=[]
def check(name,ok,detail=None):
 checks.append(dict(name=name,passed=bool(ok),detail=detail));print(name,bool(ok),str(detail or '')[:150],flush=True);assert ok,name
key=os.environ['DEEPSEEK_API_KEY']
with sync_playwright() as p:
 b=p.chromium.launch(channel='msedge',headless=True);page=b.new_page(viewport=dict(width=1536,height=850))
 errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
 page.goto(BASE,wait_until='domcontentloaded');page.wait_for_function('typeof app!=="undefined" && app.serverStats && app.charts.bar',timeout=90000)
 page.wait_for_timeout(600)
 state=page.evaluate('''() => {let c=app.charts.bar;return {axis:c.options.indexAxis,labels:c.data.labels,ticks:c.scales.y.ticks.map(t=>t.label),rotation:c.scales.y.labelRotation,height:c.height};}''')
 check('live horizontal chart complete labels',state['axis']=='y' and state['ticks']==state['labels'] and state['rotation']==0 and state['height']==130,state)
 page.locator('#games-toggle').click()
 pills=page.locator('#games-panel .games-grid a')
 check('six original colored capsules',pills.count()==6 and pills.evaluate_all('(links)=>links.every(l=>parseFloat(getComputedStyle(l).borderRadius)>=100 && getComputedStyle(l).backgroundImage.includes("gradient"))'))
 page.locator('#games-close').click()
 check('bold correct affiliation and lab link',page.evaluate('''() => {let text=document.querySelector('.brand-subtitle') || document.querySelector('.brand-affiliation');return document.body.textContent.includes('方舟实验室 · 郑州大学地球科学与技术学院 · 郑州市自然保护地事务中心') && !!document.querySelector('a[href="https://3.1415926.love/arklb-geoai/"]');}'''))
 page.evaluate('app.toggleAIAssistant(true)')
 with page.expect_response(lambda r:r.url.endswith('/api/ai/chat/') and r.request.method=='POST',timeout=60000) as resp:
  page.locator('#ai-agent-input').fill('请用一句话概括当前全部监测记录和鸟类数量。');page.locator('#ai-agent-send').click()
 response=resp.value;payload=response.json()
 check('production Xiaozhou upstream response',response.status==200 and payload.get('model')=='deepseek-chat' and payload.get('deepseek_error') is None,dict(model=payload.get('model'),error=payload.get('deepseek_error'),answer_length=len(payload.get('answer',''))))
 page.wait_for_function('!document.querySelector(".ai-msg.loading")')
 check('key absent from HTML and AI JSON',key not in page.content() and key not in json.dumps(payload))
 page.screenshot(path='docs/monitoring_validation/production-ai.png')
 page.evaluate('app.toggleAIAssistant(false)');page.wait_for_timeout(400);page.screenshot(path='docs/monitoring_validation/production-desktop.png')
 for path in ('/.env.local','/.git/config','/static/.env.local','/.monitoring-release.json','/etc/xuan1203/ai.env'):
  r=page.request.get(BASE+path);check('configuration inaccessible '+path,r.status in (403,404))
 for path in ('/species/','/articles/','/image-gallery/','/bird-guess/','/bird-runner/','/migration/','/wetland-restorer/','/wetland-detective/','/floating-island/','/arklb-geoai/'):
  r=page.request.get(BASE+path);check('preserved page '+path,r.status==200)
 check('no browser errors',not errors,errors)
 b.close()
Path('docs/monitoring_validation/production-smoke-results.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2),encoding='utf-8')
