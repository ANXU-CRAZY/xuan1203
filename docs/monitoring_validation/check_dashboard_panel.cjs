const fs = require('fs');
const {chromium} = require('C:/Users/Xuan/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const root = require('path').resolve(__dirname, '../..').replaceAll('\\', '/') + '/';
const base = 'https://3.1415926.love';
const output = root + 'docs/monitoring_validation/';
const live = process.argv.includes('--live');
(async () => {
  const browser = await chromium.launch({channel:'msedge', headless:true});
  const results = [];
  for (const [width,height] of [[1440,1000],[1280,800],[768,1024],[390,844]]) {
    const page = await browser.newPage({viewport:{width,height}});
    const errors=[];
    page.on('pageerror', e => errors.push(String(e)));
    if (!live) {
      await page.route(base+'/', r => r.fulfill({contentType:'text/html; charset=utf-8',body:fs.readFileSync(root+'app_monitor/templates/index.html','utf8').replace('{% include "app_monitor/site_theme.html" %}',fs.readFileSync(root+'app_monitor/templates/app_monitor/site_theme.html','utf8'))}));
      await page.route('**/dashboard-panel.css?*', r => r.fulfill({contentType:'text/css',body:fs.readFileSync(root+'app_monitor/static/app_monitor/dashboard-panel.css','utf8')}));
    }
    await page.goto(base+'/',{waitUntil:'domcontentloaded', timeout:60000});
    await page.waitForFunction('app.serverStats && app.charts.trend && !app._aiSending',null,{timeout:60000});
    await page.waitForTimeout(400);
    if (width<=768 && !await page.locator('#detail-panel').evaluate(e=>e.classList.contains('minimized'))) throw new Error('Mobile must start collapsed');
    await page.locator('#dashboard-overview-tab').click();
    await page.waitForTimeout(400);
    const overview = await page.evaluate(() => {
      const rect = id => {const r=document.getElementById(id).getBoundingClientRect();return {x:r.x,y:r.y,width:r.width,height:r.height,bottom:r.bottom,right:r.right}};
      return {panel:rect('detail-panel'),composer:rect('ai-agent-input'),list:rect('species-list-box'),charts:['bar','level','trend'].map(k=>({name:k,type:app.charts[k].config.type,axis:app.charts[k].options.indexAxis,labels:app.charts[k].data.labels,rotation:app.charts[k].scales.y.labelRotation})),total:app.serverStats.total_records,hasFab:!!document.querySelector('#detail-panel #ai-agent-fab .ai-agent-person'),documentOverflow:document.documentElement.scrollWidth>innerWidth};
    });
    if (overview.charts.some(c=>c.type!=='bar'||c.axis!=='y'||c.rotation!==0)) throw new Error('Chart contract failed');
    if (overview.charts[2].labels.join(',')!=='2022,2023,2024,2025,2026') throw new Error('Five-year chart failed');
    if (overview.panel.x<0||overview.panel.right>width||overview.panel.y<0||overview.panel.bottom>height||overview.documentOverflow||!overview.hasFab) throw new Error('Panel layout failed');
    await page.screenshot({path:output+`dashboard-${live?'production':'preview'}-${width}.png`});
    // Switching and collapse must retain the chat session.
    await page.locator('#ai-agent-fab').click();
    if (!await page.locator('#ai-agent-panel').isVisible()) throw new Error('Original Xiaozhou icon failed');
    await page.evaluate(()=>app.addAIMessage('user','检查会话保留'));
    await page.locator('#dashboard-overview-tab').click();
    await page.locator('#dashboard-chat-tab').click();
    if (!await page.locator('#ai-agent-messages').innerText().then(t=>t.includes('检查会话保留'))) throw new Error('Chat session lost');
    await page.screenshot({path:output+`dashboard-chat-${live?'production':'preview'}-${width}.png`});
    await page.locator('#dashboard-collapse').click();
    if (!await page.locator('#detail-panel').evaluate(e=>e.classList.contains('minimized'))) throw new Error('Collapse failed');
    if (!await page.locator('#dashboard-chat-tab').isVisible()) throw new Error('Collapsed tabs clipped');
    await page.locator('#dashboard-chat-tab').click();
    if (!await page.locator('#ai-agent-input').isVisible()) throw new Error('Reopen failed');
    if (width===1440) {
      const responsePromise=page.waitForResponse(r=>r.url().endsWith('/api/ai/chat/')&&r.request().method()==='POST',{timeout:60000});
      await page.locator('#ai-agent-input').fill('请用一句话概括当前地图的观测记录数和鸟类数量。');
      await page.locator('#ai-agent-send').click();
      const response=await responsePromise; const payload=await response.json();
      if (response.status()!==200||payload.deepseek_error||payload.model==='local-data-summary') throw new Error('Upstream AI failed');
      await page.waitForFunction('!app._aiSending');
      results.push({ai:{status:response.status(),model:payload.model,answerLength:payload.answer.length}});
      await page.screenshot({path:output+`dashboard-ai-${live?'production':'preview'}.png`});
    }
    if(errors.length) throw new Error(errors.join('\n'));
    results.push({width,height,overview,errors});
    await page.close();
  }
  fs.writeFileSync(output+`dashboard-panel-${live?'production':'preview'}-results.json`,JSON.stringify(results,null,2));
  console.log(JSON.stringify(results,null,2));
  await browser.close();
})().catch(e=>{console.error(e);process.exit(1)});
