const metrics = {individuals: '累计观测只数', species: '已识别物种数', records: '观测记录数'};
const colors = ['#a6acaa', '#96cece', '#468b99', '#125368'];
const surveyQuestion = /(?=.*(?:河边|河旁|沿河|沿岸|河段))(?=.*(?:鸟|观测|物种))(?=.*(?:哪|多少|最多|比较|排名|调查|统计))/;
const explicitGisOperation = /(?:缓冲(?:区)?|\bbuffer\b|空间(?:连接|叠加|筛选|查询)|叠加分析|裁剪|相交|擦除|插值|栅格化|矢量化|(?:筛选|筛出|提取).{0,12}(?:区内|面内|点|要素|图层)|(?:生成|创建|执行).{0,12}(?:图层|缓冲|空间|插值|栅格|矢量)|定位图层|切换底图|(?:改成|换成|切换到?).{0,8}(?:图层|地图|卫星|底图|热力|缓冲|栅格|矢量))/i;
const followup = /^(?:(?:那|再|改(?:成|为)?|把|按|只看|换(?:成|为)?|这张|刚才).{0,32}(?:种类|种数|只数|记录数|月份?|(?:上|本|下)个月|今年|去年|20\d{2}(?:年|-\d{2})|公里|千米|米|河段|河道|沿岸|物种|鸟|观测来源|数据来源|模拟观测|平台已审核|横版|A4|专题图)|(?:种类|种数|只数|记录数)(?:来算|看|统计)?[。？!?]*$|(?:导出|做成|排成|出图).{0,32}(?:横版|A4|专题图)|(?:只看|改成|改为|换成)[\u4e00-\u9fff]{1,6}(?:呢|吧|即可)?[。！]?)/;

function wantsRiverSurvey(message) {
    return !explicitGisOperation.test(message) && surveyQuestion.test(message);
}

function previousMonth() {
    const [year, month] = new Intl.DateTimeFormat('sv-SE', {timeZone: 'Asia/Shanghai',
        year: 'numeric', month: '2-digit'}).format(new Date()).split('-').map(Number);
    return new Date(Date.UTC(year, month - 2, 1)).toISOString().slice(0, 7);
}

function summary(result, metric) {
    const observed = result.reaches.filter(r => r.records);
    if (!observed.length) return '所选月份和范围内没有有效记录，无法比较河段。';
    const max = Math.max(...observed.map(r => r[metric]));
    const leaders = observed.filter(r => r[metric] === max);
    const leader = leaders[0];
    let text = leaders.map(r => r.name).join('、') + (leaders.length > 1 ? '并列第一' : '居首') +
        '，' + metrics[metric] + '为 ' + max + '。' + leader.name + '的数据来自 ' +
        leader.days + ' 个有记录日、' + leader.records + ' 条观测。';
    if (metric === 'individuals') {
        const byDay = observed.reduce((best, r) => r.individuals / r.days > best.individuals / best.days ? r : best);
        text += '按有记录日平均，' + byDay.name + '为 ' + (byDay.individuals / byDay.days).toFixed(1) +
            ' 只/日。重复观测和调查频次都会影响累计值。';
    }
    const missing = observed.reduce((n, r) => n + r.missing_species, 0);
    if (missing && metric === 'species') text += '有 ' + missing + ' 条记录缺少物种标识，已排除在种数统计之外。';
    return text;
}

function colorIndex(row, metric, max) {
    if (!row.records) return 0;
    return 1 + metricBands(max).findIndex(band => row[metric] <= band.upper);
}

function metricBands(max) {
    if (max <= 1) return [{upper: max, label: max === 0 ? '0' : '0–1'}];
    if (max === 2) return [{upper: 1, label: '0–1'}, {upper: 2, label: '2'}];
    const first = Math.floor(max / 3), second = Math.floor(2 * max / 3);
    return [
        {upper: first, label: '0–' + first},
        {upper: second, label: '>' + first + '–' + second},
        {upper: max, label: '>' + second + '–' + max},
    ];
}

function legend(max) {
    return ['无有效记录', ...metricBands(max).map(band => band.label)];
}

// A standalone vector figure uses the exact reach snapshot, independent of tile loading.
function downloadLandscape(result, metric, river, bird) {
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    const append = (tag, attrs, value) => {
        const n = document.createElementNS(svg.namespaceURI, tag);
        for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
        if (value !== undefined) n.textContent = value;
        svg.append(n);
    };
    svg.setAttribute('viewBox', '0 0 1122 794');
    svg.setAttribute('width', '297mm');
    svg.setAttribute('height', '210mm');
    const label = (x, y, size, value) => append('text', {x, y, 'font-size': size,
        fill: '#193940', 'font-family': 'sans-serif'}, value);
    append('rect', {width: 1122, height: 794, fill: '#fff'});
    label(48, 66, 32, river + ' · ' + metrics[metric]);
    label(48, 104, 18, result.month + '　' + (bird || '全部物种') + '　沿岸 ' + result.radius / 1000 + ' 公里　每段 5 公里');
    const coords = result.reaches.flatMap(r => r.geometry.coordinates);
    const xs = coords.map(c => c[0]), ys = coords.map(c => c[1]);
    const west = Math.min(...xs), north = Math.max(...ys);
    const east = Math.max(...xs), south = Math.min(...ys);
    const horizontal = 111320 * Math.cos((south + north) * Math.PI / 360);
    const width = (east - west) * horizontal, height = (north - south) * 111320;
    const scale = Math.min(940 / (width || 1), 400 / (height || 1));
    const max = Math.max(...result.reaches.map(r => r[metric]));
    for (const r of result.reaches) {
        const points = r.geometry.coordinates.map(([x, y]) => [
            561 - width * scale / 2 + (x - west) * horizontal * scale,
            365 - height * scale / 2 + (north - y) * 111320 * scale]);
        append('polyline', {points: points.map(p => p.join(',')).join(' '), fill: 'none',
            stroke: colors[colorIndex(r, metric, max)], 'stroke-width': 8});
        if (result.reaches.length <= 20) {
            const [x, y] = points[Math.floor(points.length / 2)];
            label(x, y - 9, 13, r.name);
        }
    }
    label(1038, 158, 18, '↑ 北');
    const barKm = 10 ** Math.floor(Math.log10(140 / scale / 1000));
    append('rect', {x: 48, y: 592, width: scale * barKm * 1000, height: 3, fill: '#193940'});
    label(48, 586, 14, '约 ' + barKm + ' km');
    legend(max).forEach((name, i) => {
        append('rect', {x: 48 + i * 220, y: 628, width: 32, height: 8, fill: colors[i]});
        label(87 + i * 220, 639, 15, name);
    });
    label(48, 701, 17, '观测来源　' + result.source);
    label(48, 739, 16, '方舟视界　·　归属至最近河道里程　·　距离计算 EPSG:' + result.epsg);
    const url = URL.createObjectURL(new Blob([new XMLSerializer().serializeToString(svg)], {type: 'image/svg+xml'}));
    const link = document.createElement('a');
    link.href = url; link.download = '河段调查-' + result.month + '-' + metrics[metric] + '-横版.svg';
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 30000);
}

export function createRiverSurvey({form, input, status, getMapVersion, refreshLayers, stepRow, layerBounds}) {
    const options = document.querySelector('#wb-survey-options');
    const output = document.querySelector('#wb-survey-results');
    const controls = options.elements;
    const example = document.querySelector('#wb-survey-example');
    let version, previous, submitted = false, printRequested = false;
    const request = async (url, data, signal) => {
        const response = await fetch(url, {method: 'POST', signal, headers: {'Content-Type': 'application/json',
            'X-CSRFToken': form.elements.csrfmiddlewaretoken.value}, body: JSON.stringify(data)});
        const json = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(json.detail || '调查服务暂时不可用。');
        return json;
    };
    example.onclick = () => {
        if (input.disabled) return;
        input.value = '上个月黄河边哪段水鸟最多？';
        form.requestSubmit();
    };
    options.onsubmit = event => {
        event.preventDefault();
        if (input.disabled) return;
        submitted = true;
        input.value = '执行河段调查';
        form.requestSubmit();
    };
    function reset() {
        previous = null; submitted = printRequested = false;
        options.reset(); options.hidden = output.hidden = true;
        output.replaceChildren();
    }
    async function handle(message, client, signal, check) {
        if (version !== getMapVersion()) { reset(); version = getMapVersion(); }
        const run = submitted;
        submitted = false;
        const surveyFollowup = (previous || !options.hidden) && followup.test(message) && !explicitGisOperation.test(message);
        if (!run && !wantsRiverSurvey(message) && !surveyFollowup) {
            options.hidden = output.hidden = true;
            previous = null;
            return false;
        }
        if (!run) {
            const layoutOnly = /^(?:把)?(?:这张图|上面的结果|刚才的图)?(?:做成|排成|导出|出)?(?:一张)?(?:A4\s*)?横版(?:图|给我|给老师)?[。！]?$/i.test(message);
            if (previous && layoutOnly) {
                downloadLandscape(previous.data, previous.metric, previous.river, previous.bird);
                status.textContent = '已导出上次结果的 A4 横版专题图。';
                return true;
            }
            const layers = await client.listLayers();
            check();
            const priorRiver = controls.river.value;
            controls.river.replaceChildren(...layers.filter(l => l.type === 'geojson' && !l.id.startsWith('survey-'))
                .map(l => new Option(l.name, l.id)));
            const preferred = layers.find(l => l.id === priorRiver) || layers.find(l => /河道|河段|黄河走势|中心线/.test(l.name));
            if (preferred) controls.river.value = preferred.id;
            if (!controls.month.value) {
                controls.month.value = previousMonth();
                controls.km.value = 2;
                controls.source.value = controls.river.value === 'sample-river' ? 'sample' : 'approved';
            }
            options.hidden = false;
            let note = '';
            const metricOnly = /^(?:改成|换成|再)?(?:按|看|按.*?看)?(种类|种数|只数|记录数)(?:来算|看|统计)?[。？]?$/;
            const match = message.match(metricOnly);
            if (match) {
                controls.metric.value = ({种类:'species',种数:'species',只数:'individuals',记录数:'records'})[match[1]];
            } else if (message === '上个月黄河边哪段水鸟最多？') {
                controls.month.value = previousMonth(); controls.metric.value = '';
                printRequested = false;
            } else {
                try {
                    const intent = await request(options.dataset.intentUrl, {message}, signal);
                    check();
                    if (intent.metric) controls.metric.value = intent.metric;
                    if (intent.month) controls.month.value = intent.month;
                    if (intent.radius_km) controls.km.value = intent.radius_km;
                    if (intent.bird) controls.bird.value = intent.bird;
                    printRequested = intent.landscape;
                    note = intent.limitation || '';
                } catch (err) {
                    check(); note = err.message;
                }
            }
            if (!previous || !match || note || !options.checkValidity()) {
                status.textContent = [note, controls.metric.value ? '请核对河道、月份和数据来源。' :
                    '您想比较鸟的只数、种数，还是观测记录条数？'].filter(Boolean).join(' ');
                return true;
            }
        }
        const river = controls.river.selectedOptions[0];
        if (!river) throw new Error('请先导入一条河道中心线。');
        const items = await client.getLayerFeatures(river.value);
        check();
        if (items.length !== 1 || items[0].geometry?.type !== 'LineString') {
            throw new Error('当前调查按一条连续中心线的里程分段，请选择单条 LineString 河道图层。');
        }
        const params = {source: controls.source.value, coordinates: items[0].geometry.coordinates,
            month: controls.month.value, radius: Number(controls.km.value) * 1000, bird: controls.bird.value.trim()};
        const key = JSON.stringify(params);
        const metric = controls.metric.value;
        const done = stepRow('按最近河道里程归属观测，汇总各段');
        let data;
        try {
            data = previous?.key === key ? previous.data : await request(form.dataset.surveyUrl, params, signal);
            check();
            done('done', (previous?.key === key ? '沿用上次统计 · ' : '') + data.reaches.length + ' 个河段');
        } catch (error) { done('error', error.message); throw error; }
        const max = Math.max(...data.reaches.map(r => r[metric]));
        const features = data.reaches.map(r => ({type: 'Feature', geometry: r.geometry, properties: {
            河段: r.name, 起点公里: r.start_km, 终点公里: r.end_km, 累计只数: r.individuals, 已识别物种数: r.species,
            记录数: r.records, 观测天数: r.days, stroke: colors[colorIndex(r, metric, max)]}}));
        const id = 'survey-' + crypto.randomUUID();
        await client.addLayer({id, type: 'geojson', name: [data.source.split('（')[0], data.month, metrics[metric]].join(' · '),
            source: {type:'geojson'}, style:{simpleStyleEnabled:true, strokeWidth:6, strokeColor:colors[2]},
            geojson:{type:'FeatureCollection', features}});
        check();
        if (previous && (await client.listLayers()).some(l => l.id === previous.id)) await client.setLayerVisibility(previous.id, false);
        await refreshLayers();
        await client.setView(layerBounds(features));
        check();
        previous = {key, id, data, metric, river:river.text, bird:params.bird};
        const ranked = [...data.reaches].sort((a,b) => b[metric] - a[metric] || a.start_km - b.start_km);
        const table = document.createElement('table');
        const headers = table.createTHead().insertRow();
        for (const name of ['河段', metrics[metric], '观测天数']) {
            const th = document.createElement('th'); th.textContent = name; headers.append(th);
        }
        const body = table.createTBody();
        for (const r of ranked) {
            const row = body.insertRow();
            for (const value of [r.name, r.records ? r[metric] : '无有效记录', r.days]) row.insertCell().textContent = value;
        }
        const download = document.createElement('button');
        download.type = 'button'; download.className = 'wb-button'; download.textContent = '下载 A4 横版专题图';
        const riverName = river.text;
        download.onclick = () => downloadLandscape(data, metric, riverName, params.bird);
        output.replaceChildren(download, table);
        output.hidden = false; options.hidden = true;
        status.textContent = data.month + ' · ' + data.source + ' · ' + riverName + '。' + summary(data, metric);
        if (printRequested) { download.click(); printRequested = false; }
        return true;
    }
    return {handle};
}
