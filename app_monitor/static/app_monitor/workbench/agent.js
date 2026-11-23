const TOOL_NAMES = {
    layers: '查看图层', overview: '研究区全览', locate: '定位图层', visibility: '设置图层显隐',
    basemap: '切换底图', buffer: '生成缓冲区', points_within: '筛选区内点',
    count: '统计要素条数', idw: '反距离权重插值', export_png: '导出地图图片',
};
const BASEMAP_NAMES = {vector: '天地图电子图', imagery: '天地图影像', amap: '高德地图', blank: '无底图'};
const VECTOR_NAMES = {
    centroids: '提取质心', convex_hull: '凸包', bounding_box: '包围框', dissolve: '融合',
    explode: '多部件拆分', smooth: '平滑', extract_vertices: '提取顶点',
    clip: '裁剪', intersection: '求交', difference: '擦除', union: '合并',
};
Object.assign(TOOL_NAMES, VECTOR_NAMES);
const EXAMPLE = '找出离黄河走势 2 公里内的水鸟观测点，数一下有几条记录。';
const NATIVE_TOOL_NAMES = {
    list_layers: '读取图层', list_algorithms: '查找空间分析工具',
    run_algorithm: '执行矢量分析', list_whitebox_tools: '查找栅格分析工具',
    run_whitebox_tool: '执行栅格分析', list_model_algorithms: '查找模型工具',
    create_model_builder_model: '创建分析模型', zoom_to: '定位地图',
    set_basemap: '切换底图', run_sql: '统计与查询',
};

function describeNativeTool(update, layerNames) {
    const tool = update.input?.id;
    const label = (update.name === 'run_algorithm' && ANALYSIS_LABELS[tool]) || NATIVE_TOOL_NAMES[update.name] || update.name;
    const params = update.input?.params;
    const values = Object.entries(params || {}).slice(0, 6)
        .filter(([, value]) => ['string', 'number', 'boolean'].includes(typeof value))
        .map(([key, value]) => key + '＝' + String(layerNames.get(value) || value).slice(0, 70));
    return [tool ? label + ' · ' + tool : label, values.join('，')];
}

const ANALYSIS_LABELS = JSON.parse(document.getElementById('wb-analysis-labels')?.textContent || '{}');
const STATISTICS_ONLY = new Set(['average-nearest-neighbor', 'global-morans-i', 'run_sql']);
const TOOL_PURPOSES = {
    buffer: '将指定距离转换为可用于筛选的地理范围。',
    points_within: '按范围保留落入其中的点，供查阅或统计。',
    count: '统计输入图层中的记录数。',
    clip: '沿指定边界裁切输入图层，保留其中的部分。',
    intersection: '提取两个图层共同覆盖的范围。',
    difference: '从输入范围中扣除指定区域。',
    idw: '用附近采样点的测量值估计未测位置。',
    'kernel-density': '根据点的位置和带宽估计观测密度。',
    'getis-ord-gi': '检验在指定邻域中，高值和低值是否显著聚集。',
    run_sql: '按所选字段和统计口径汇总工程数据。',
};

function moveWithin(workspace, element, x, y) {
    const margin = 8;
    const at = (value, available) => Math.max(margin, Math.min(value, available - margin));
    element.style.left = at(x, workspace.clientWidth - element.offsetWidth) + 'px';
    element.style.top = at(y, workspace.clientHeight - element.offsetHeight) + 'px';
    element.style.right = element.style.bottom = 'auto';
}

function makeDraggable(workspace, element, handle) {
    let drag;
    let suppressClick = false;
    handle.addEventListener('pointerdown', event => {
        if (drag || !event.isPrimary || event.button !== 0 ||
            (handle !== element && event.target.closest('button'))) return;
        suppressClick = false;
        drag = {id: event.pointerId, startX: event.clientX, startY: event.clientY,
            x: element.offsetLeft, y: element.offsetTop, moved: false};
        if (event.pointerType === 'mouse') handle.setPointerCapture(event.pointerId);
    });
    handle.addEventListener('pointermove', event => {
        if (event.pointerId !== drag?.id) return;
        const dx = event.clientX - drag.startX;
        const dy = event.clientY - drag.startY;
        if (!drag.moved && Math.hypot(dx, dy) < 5) return;
        if (!drag.moved) handle.setPointerCapture(event.pointerId);
        drag.moved = suppressClick = true;
        element.dataset.moved = 'true';
        workspace.classList.add('wb-agent-dragging');
        moveWithin(workspace, element, drag.x + dx, drag.y + dy);
    });
    function finish(event) {
        if (event.pointerId !== drag?.id) return;
        const tap = event.type === 'pointerup' && event.pointerType === 'touch' && handle === element && !drag.moved;
        drag = null;
        workspace.classList.remove('wb-agent-dragging');
        if (tap) {
            // Some touch browsers suppress the first synthesized click after a drag.
            suppressClick = true;
            handle.click();
        }
    }
    for (const type of ['pointerup', 'pointercancel', 'lostpointercapture']) handle.addEventListener(type, finish);
    handle.addEventListener('click', event => {
        if (!suppressClick || event.detail === 0 || (handle !== element && event.target.closest('button'))) return;
        suppressClick = false;
        event.preventDefault();
        event.stopImmediatePropagation();
    }, true);
    const directions = {ArrowUp: [0, -1], ArrowDown: [0, 1], ArrowLeft: [-1, 0], ArrowRight: [1, 0]};
    handle.addEventListener('keydown', event => {
        if (event.target !== handle || !directions[event.key]) return;
        const [x, y] = directions[event.key];
        event.preventDefault();
        element.dataset.moved = 'true';
        const distance = event.shiftKey ? 40 : 12;
        moveWithin(workspace, element, element.offsetLeft + x * distance, element.offsetTop + y * distance);
    });
}

function layerBounds(features) {
    const bounds = [Infinity, Infinity, -Infinity, -Infinity];
    function visit(value) {
        if (!Array.isArray(value)) return;
        const [x, y] = value;
        if (Number.isFinite(x) && Number.isFinite(y) && Math.abs(x) <= 180 && Math.abs(y) <= 90) {
            bounds[0] = Math.min(bounds[0], x);
            bounds[1] = Math.min(bounds[1], y);
            bounds[2] = Math.max(bounds[2], x);
            bounds[3] = Math.max(bounds[3], y);
        } else {
            value.forEach(visit);
        }
    }
    function geometry(shape) {
        if (shape?.type === 'GeometryCollection') shape.geometries.forEach(geometry);
        else visit(shape?.coordinates);
    }
    features.forEach(feature => geometry(feature.geometry));
    if (!bounds.every(Number.isFinite)) throw new Error('这个图层没有可定位的地理要素。');
    if (bounds[0] === bounds[2] && bounds[1] === bounds[3]) return {center: bounds.slice(0, 2), zoom: 13};
    return {bbox: bounds};
}

function runGeometry(url, payload, signal) {
    signal.throwIfAborted();
    return new Promise((resolve, reject) => {
        const worker = new Worker(url);
        function finish(callback, value) {
            clearTimeout(timer);
            signal.removeEventListener('abort', cancel);
            worker.terminate();
            callback(value);
        }
        const cancel = () => finish(reject, signal.reason);
        const timer = setTimeout(() => finish(reject, new Error('空间分析超时，请缩小数据范围。')), 15000);
        signal.addEventListener('abort', cancel, {once: true});
        worker.onmessage = ({data}) => data.detail
            ? finish(reject, new Error(data.detail)) : finish(resolve, data);
        worker.onerror = () => finish(reject, new Error('空间分析组件无法加载。'));
        worker.postMessage(payload);
    });
}

export function initAgent({getClient, getNativeFrame, getMapVersion, region, geometryUrl, setBasemap, exportMap, refreshLayers}) {
    const panel = document.getElementById('wb-agent');
    const toggle = document.getElementById('wb-agent-toggle');
    const close = document.getElementById('wb-agent-close');
    const form = document.getElementById('wb-agent-form');
    const input = document.getElementById('wb-agent-input');
    const run = document.getElementById('wb-agent-run');
    const stop = document.getElementById('wb-agent-stop');
    const preview = document.getElementById('wb-agent-plan');
    const goal = document.getElementById('wb-agent-goal');
    const previewSteps = document.getElementById('wb-agent-preview');
    const example = document.getElementById('wb-agent-example');
    const status = document.getElementById('wb-agent-status');
    const list = document.getElementById('wb-agent-steps');
    const workspace = panel.parentElement;
    const scroll = panel.querySelector('.wb-agent-content');
    let task;

    makeDraggable(workspace, toggle, toggle);
    makeDraggable(workspace, panel, panel.querySelector('.wb-agent-heading'));
    function alignPanel() {
        if (panel.hidden) return;
        if (panel.dataset.moved) {
            moveWithin(workspace, panel, panel.offsetLeft, panel.offsetTop);
        } else if (toggle.dataset.moved) {
            const above = toggle.offsetTop - panel.offsetHeight - 8;
            const below = toggle.offsetTop + toggle.offsetHeight + 8;
            moveWithin(workspace, panel, toggle.offsetLeft + toggle.offsetWidth - panel.offsetWidth,
                above >= 8 || below + panel.offsetHeight > workspace.clientHeight ? above : below);
        } else if (panel.offsetTop < 8) {
            moveWithin(workspace, panel, panel.offsetLeft, 8);
        } else if (panel.style.top) {
            for (const side of ['top', 'left', 'right', 'bottom']) panel.style.removeProperty(side);
            if (panel.offsetTop < 8) moveWithin(workspace, panel, panel.offsetLeft, 8);
        }
    }
    const resize = new ResizeObserver(() => {
        if (toggle.dataset.moved) moveWithin(workspace, toggle, toggle.offsetLeft, toggle.offsetTop);
        alignPanel();
    });
    resize.observe(workspace);
    resize.observe(panel);
    function openPanel(open) {
        panel.hidden = !open;
        toggle.setAttribute('aria-expanded', String(open));
        alignPanel();
        (open ? panel.querySelector('.wb-agent-heading') : toggle).focus({preventScroll: true});
    }
    toggle.onclick = () => openPanel(panel.hidden);
    close.onclick = () => openPanel(false);
    close.addEventListener('pointerup', event => {
        if (event.pointerType === 'touch' && document.elementFromPoint(event.clientX, event.clientY)?.closest('button') === close) {
            openPanel(false);
        }
    });
    panel.addEventListener('keydown', event => { if (event.key === 'Escape') openPanel(false); });
    example.onclick = () => { input.value = EXAMPLE; input.focus(); };
    input.addEventListener('keydown', event => {
        if (event.key !== 'Enter' || event.shiftKey || event.altKey || event.ctrlKey || event.metaKey ||
            event.isComposing || event.keyCode === 229) return;
        event.preventDefault();
        if (!task && !event.repeat) form.requestSubmit(run);
    });
    stop.onclick = () => task?.abort();
    window.addEventListener('pagehide', () => task?.abort());

    function stepRow(label) {
        const row = document.createElement('li');
        const title = document.createElement('span');
        const detail = document.createElement('small');
        title.textContent = label;
        detail.textContent = '执行中…';
        row.append(title, detail);
        list.append(row);
        scroll.scrollTop = scroll.scrollHeight;
        return (state, text) => { row.dataset.state = state; detail.textContent = text; };
    }

    function describePlanStep(step, refs) {
        const label = step.tool === 'native' ? ANALYSIS_LABELS[step.method] : TOOL_NAMES[step.tool];
        const describeRef = ref => refs.get(ref)?.name || '第 ' + ref.slice(1) + ' 步成果';
        const parameters = [];
        if (step.inputs) parameters.push(step.inputs.map(describeRef).join('、'));
        if (step.layer) parameters.push(describeRef(step.layer));
        if (step.area) parameters.push('范围 ' + describeRef(step.area));
        if (step.meters) parameters.push(step.meters + ' 米');
        if (step.field) parameters.push('字段 ' + step.field);
        if (step.kind) parameters.push(BASEMAP_NAMES[step.kind]);
        if (typeof step.visible === 'boolean') parameters.push(step.visible ? '显示' : '隐藏');
        for (const [name, value] of Object.entries(step.parameters || {})) parameters.push(name + ' ' + value);
        return {label, detail: parameters.join(' · ')};
    }

    function setBusy(busy) {
        input.disabled = run.disabled = example.disabled = busy;
        run.hidden = busy;
        stop.hidden = !busy;
    }

    async function describeLayers(client, layers, message, native) {
        const vector = layers.filter(layer => layer.type === 'geojson');
        const candidates = vector.length <= 4 ? vector : vector.filter(layer =>
            message.includes(layer.name.replace(/[（(][^（）()]*[）)]$/, ''))).slice(0, 4);
        const schemas = new Map();
        if (native) {
            await Promise.all(candidates.map(async layer => {
                let items;
                try { items = await client.getLayerFeatures(layer.id); } catch { return; }
                const geometry = new Set(), fields = new Set(), numericFields = new Set();
                for (const item of items.slice(0, 120)) {
                    if (item.geometry?.type) geometry.add(item.geometry.type);
                    for (const [name, value] of Object.entries(item.properties || {})) {
                        if (fields.size < 32) fields.add(name);
                        if (Number.isFinite(value) && numericFields.size < 24) numericFields.add(name);
                    }
                }
                schemas.set(layer.id, {geometry: [...geometry], fields: [...fields],
                    ...(items.length <= 120 ? {numericFields: [...numericFields]} : {})});
            }));
        }
        return layers.map(layer => ({name: layer.name, type: layer.type,
            ...(native ? schemas.get(layer.id) : client.describeAnalysisLayer?.(layer.id))}));
    }

    form.addEventListener('submit', async event => {
        event.preventDefault();
        const client = getClient();
        const message = input.value.trim();
        if (task || !client || !message) return;
        preview.hidden = true;
        list.replaceChildren();
        status.textContent = '正在将描述转换为 GIS 工具方案…';
        task = new AbortController();
        const {signal} = task;
        const version = getMapVersion();
        setBusy(true);
        try {
            const nativeFrame = getNativeFrame?.();
            const layers = await client.listLayers();
            const metadata = await describeLayers(client, layers, message, Boolean(nativeFrame));
            const response = await fetch(form.dataset.planUrl, {
                method: 'POST', signal: AbortSignal.any([signal, AbortSignal.timeout(32000)]),
                headers: {'Content-Type': 'application/json', 'X-CSRFToken': form.elements.csrfmiddlewaretoken.value},
                body: JSON.stringify({message, allowNative: Boolean(nativeFrame), layers: metadata}),
            });
            const plan = await response.json().catch(() => ({}));
            if (!response.ok || !Array.isArray(plan.steps)) throw new Error(plan.detail || '方案生成失败，请重试。');
            signal.throwIfAborted();
            if (client !== getClient() || version !== getMapVersion()) throw new Error('工程已切换，请重新生成方案。');
            if (!plan.steps.length) {
                status.textContent = plan.message || '请补充分析目标、图层或参数。';
                return;
            }
            const refs = new Map(layers.map((layer, index) => ['L' + (index + 1), layer]));
            const rows = plan.steps.map((step, index) => {
                const {label, detail} = describePlanStep(step, refs);
                const row = document.createElement('li');
                row.textContent = label;
                if (detail) {
                    const item = document.createElement('small');
                    item.textContent = detail;
                    row.append(item);
                }
                const purpose = TOOL_PURPOSES[step.method || step.tool] || plan.reasons?.[index];
                if (purpose) {
                    const note = document.createElement('small');
                    note.textContent = purpose;
                    row.append(note);
                }
                return row;
            });
            previewSteps.replaceChildren(...rows);
            goal.textContent = '任务理解：' + (plan.goal || rows.map(row => row.firstChild.textContent).join(' → '));
            preview.hidden = false;
            scroll.scrollTop = 0;
            await executePlan({client, message, version, plan, refs, nativeFrame, signal});
        } catch (error) {
            status.textContent = signal.aborted ? '已停止生成方案。' :
                error.name === 'TimeoutError' ? '方案生成超时，请稍后重试。' : error.message;
        } finally {
            task = null;
            setBusy(false);
        }
    });

    async function executePlan({client, message, version, plan, refs, nativeFrame, signal}) {
        status.textContent = '正在执行分析…';
        let completed = 0;
        let markStep;
        let lastResult = '';
        const pending = new Map();
        const native = plan.steps.some(step => step.tool === 'native');

        function checkTask() {
            signal.throwIfAborted();
            if (getClient() !== client || getMapVersion() !== version) throw new Error('工程已切换，请重新提交任务。');
        }
        async function getLayer(ref) {
            const layer = refs.get(ref);
            const current = (await client.listLayers()).find(item => item.id === layer?.id);
            if (!current) throw new Error('任务引用的图层已移除。');
            return current;
        }
        async function features(layer) {
            if (layer.type !== 'geojson') throw new Error('该操作需要已加载的 GeoJSON 矢量图层。');
            return client.getLayerFeatures(layer.id);
        }
        async function execute(step, index) {
            const layer = step.layer ? await getLayer(step.layer) : null;
            checkTask();
            switch (step.tool) {
                case 'layers': {
                    const layers = await client.listLayers();
                    return layers.length ? layers.map(item => item.name).join('、') : '当前没有图层';
                }
                case 'overview':
                    await client.setView(region);
                    return '已回到研究区全览';
                case 'locate': {
                    const bounds = layerBounds(await features(layer));
                    checkTask();
                    await client.setView(bounds);
                    return '已定位到 ' + layer.name;
                }
                case 'visibility':
                    await client.setLayerVisibility(layer.id, step.visible);
                    return (step.visible ? '已显示 ' : '已隐藏 ') + layer.name;
                case 'basemap':
                    await setBasemap(step.kind);
                    return '已切换到 ' + BASEMAP_NAMES[step.kind];
                case 'count': {
                    const items = await features(layer);
                    return layer.name + '共 ' + items.length + ' 个要素';
                }
                case 'buffer':
                case 'points_within': {
                    const items = await features(layer);
                    const areas = step.area ? await features(await getLayer(step.area)) : [];
                    checkTask();
                    const {features: output} = await runGeometry(geometryUrl, {tool: step.tool, features: items, areas, meters: step.meters}, signal);
                    checkTask();
                    const name = step.tool === 'buffer' ? layer.name + ' · ' + step.meters + ' 米缓冲区' : layer.name + ' · 区内点';
                    const id = 'agent-' + crypto.randomUUID();
                    const style = step.tool === 'buffer'
                        ? {fillColor: '#4ea798', fillOpacity: .28, strokeColor: '#147c79', strokeWidth: 2}
                        : {fillColor: '#eaa439', fillOpacity: 1, strokeColor: '#fff', strokeWidth: 1.5, circleRadius: 7};
                    await client.addLayer({id, name, type: 'geojson', source: {type: 'geojson'}, style,
                        geojson: {type: 'FeatureCollection', features: output}});
                    refs.set('R' + index, {id, name});
                    await refreshLayers();
                    return name + '，共 ' + output.length + ' 个要素';
                }
                case 'idw': {
                    const items = await features(layer);
                    const fields = [...new Set(items.flatMap(item => Object.entries(item.properties || {})
                        .filter(([key, value]) => Number.isFinite(value) &&
                            !/^(?:id|fid|gid|objectid|oid|lon|lng|lat|longitude|latitude|经度|纬度|编号)$/i.test(key))
                        .map(([key]) => key)))];
                    const named = fields.filter(field => step.field ? field === step.field : message.includes(field));
                    const field = named.length === 1 ? named[0] : !step.field && named.length === 0 && fields.length === 1 ? fields[0] : null;
                    if (!field) throw new Error(fields.length
                        ? '请指定用于插值的数值字段，可选字段：' + fields.join('、')
                        : '该点图层没有数值字段，请先添加用于插值的观测值。');
                    checkTask();
                    const {features: output, meta} = await runGeometry(geometryUrl, {tool: 'idw', features: items, field}, signal);
                    checkTask();
                    const name = layer.name + ' · IDW 插值（' + field + '）';
                    const id = 'agent-' + crypto.randomUUID();
                    await client.addLayer({
                        id, name, type: 'geojson', source: {type: 'geojson'},
                        style: {fillColor: '#52a5b3', fillOpacity: .72, strokeWidth: 0, strokeOpacity: 0, simpleStyleEnabled: true},
                        metadata: {description: 'IDW 插值结果，WGS84 点范围内 32×32 网格，球面距离，幂次 2。', idw: meta},
                        geojson: {type: 'FeatureCollection', features: output},
                    });
                    refs.set('R' + index, {id, name});
                    await refreshLayers();
                    await client.setView(layerBounds(output));
                    return field + '，有效点 ' + meta.sampleCount + ' 个，范围 ' +
                        meta.min.toFixed(2) + '–' + meta.max.toFixed(2) +
                        '，32×32 网格、幂次 2。颜色由蓝到橙表示数值从低到高。' +
                        (meta.skipped ? '跳过无数值点 ' + meta.skipped + ' 个。' : '');
                }
                case 'export_png':
                    await exportMap(signal);
                    return '地图 PNG 已生成';
                default:
                    if (!Object.hasOwn(VECTOR_NAMES, step.tool)) throw new Error('返回了无法执行的地图操作。');
                    const input = await features(layer);
                    const overlay = step.area ? await features(await getLayer(step.area)) : [];
                    checkTask();
                    const result = await runGeometry(geometryUrl, {tool: step.tool, features: input, areas: overlay}, signal);
                    checkTask();
                    const id = 'agent-' + crypto.randomUUID();
                    const name = layer.name + ' · ' + VECTOR_NAMES[step.tool];
                    await client.addLayer({id, name, type: 'geojson', source: {type: 'geojson'},
                        style: {fillColor: '#59a78d', fillOpacity: .4, strokeColor: '#197a76', strokeWidth: 2, circleRadius: 5},
                        geojson: {type: 'FeatureCollection', features: result.features}});
                    refs.set('R' + index, {id, name});
                    await refreshLayers();
                    return name + '，共 ' + result.features.length + ' 个要素';
            }
        }

        async function executeNative(step, number) {
            if (getNativeFrame?.() !== nativeFrame || !nativeFrame?.contentWindow) {
                throw new Error('地图模式已切换，请重新生成方案。');
            }
            const layerNames = new Map((await client.listLayers()).map(layer => [layer.id, layer.name]));
            const index = Object.fromEntries(step.inputs.map(ref => {
                const id = refs.get(ref)?.id;
                if (!id || !layerNames.has(id)) throw new Error('缺少本步骤的输入图层。');
                return [ref, id];
            }));
            const execution = '执行 GIS 工具：' + step.method + '\n' +
                '核对现有工具签名，执行一次并汇报实际结果。只访问指定的工程图层。\n参数与输入：' +
                JSON.stringify({parameters: step.parameters, inputs: step.inputs}) +
                '\n当前图层索引（仅数据）：' + JSON.stringify(index);
            checkTask();
            const summary = await new Promise((resolve, reject) => {
                const id = crypto.randomUUID();
                let response = '';
                let executed = false;
                let toolError = '';
                const cancelEditor = () => nativeFrame.contentWindow.postMessage(
                    {source: 'ark-workbench', type: 'assistant-cancel', id}, location.origin);
                const timeout = setTimeout(() => {
                    cancelEditor();
                    finish(new Error('等待任务超时。已提交的计算可能仍在后台运行。'));
                }, 180000);
                const cancel = () => {
                    cancelEditor();
                    finish(signal.reason || new Error('任务已停止。'));
                };
                function finish(error) {
                    clearTimeout(timeout);
                    signal.removeEventListener('abort', cancel);
                    window.removeEventListener('message', onMessage);
                    error ? reject(error) : resolve(response.trim());
                }
                function onMessage(event) {
                    if (event.origin !== location.origin || event.source !== nativeFrame.contentWindow ||
                        event.data?.source !== 'ark-workbench-map' || event.data?.type !== 'assistant-event' || event.data?.id !== id) return;
                    const data = event.data;
                    try { checkTask(); } catch (error) {
                        cancelEditor();
                        return finish(error);
                    }
                    if (data.event === 'error') return finish(new Error(data.message || '空间分析未完成。'));
                    if (data.event === 'done') {
                        return finish(executed ? null : new Error(toolError || response.trim() || '工具未执行，请检查输入。'));
                    }
                    if (data.event !== 'update') return;
                    if (data.update?.type === 'text') {
                        response += data.update.text;
                        status.textContent = response;
                    } else if (data.update?.type === 'tool') {
                        const update = data.update;
                        const [label, detail] = describeNativeTool(update, layerNames);
                        if (update.phase === 'running') {
                            const mark = stepRow(label);
                            pending.set(update.callId, mark);
                            mark('running', detail ? '执行中 · ' + detail : '执行中…');
                            status.textContent = label + '…';
                            return;
                        }
                        const mark = pending.get(update.callId) || stepRow(label);
                        pending.delete(update.callId);
                        mark(update.error ? 'error' : 'done', update.error || (detail ? '已返回 · ' + detail : '已返回'));
                        if (['run_algorithm', 'run_whitebox_tool', 'run_sql'].includes(update.name)) {
                            if (update.error) toolError = update.error;
                            else executed = true;
                        }
                    }
                }
                signal.addEventListener('abort', cancel, {once: true});
                window.addEventListener('message', onMessage);
                nativeFrame.contentWindow.postMessage({source: 'ark-workbench', type: 'assistant-run', id,
                    prompt: execution}, location.origin);
            });
            const added = (await client.listLayers()).filter(layer => !layerNames.has(layer.id));
            checkTask();
            if (!STATISTICS_ONLY.has(step.method)) {
                if (!added.length) throw new Error(summary || '工具未生成可用的结果图层。');
                if (added.length === 1) refs.set('R' + number, added[0]);
                await refreshLayers();
            }
            return [added.length ? '新增图层 ' + added.map(layer => layer.name).join('、') : '', summary]
                .filter(Boolean).join('\n');
        }

        try {
            checkTask();
            const plannedInputs = new Set(plan.steps.flatMap(step =>
                [step.layer, step.area, ...(step.inputs || [])].filter(ref => ref?.startsWith('L'))));
            const activeLayers = new Set((await client.listLayers()).map(layer => layer.id));
            checkTask();
            if ([...plannedInputs].some(ref => !activeLayers.has(refs.get(ref)?.id))) {
                throw new Error('方案引用的图层已移除，请重新生成方案。');
            }
            for (const [index, step] of plan.steps.entries()) {
                checkTask();
                status.textContent = '正在执行第 ' + (index + 1) + ' / ' + plan.steps.length + ' 步';
                markStep = stepRow(describePlanStep(step, refs).label);
                await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
                const result = step.tool === 'native' ? await executeNative(step, index + 1) : await execute(step, index + 1);
                markStep('done', result);
                lastResult = step.tool === 'count' ? result : '';
                completed++;
                markStep = null;
            }
            checkTask();
            status.textContent = '任务完成，共执行 ' + completed + ' 步。' + lastResult;
            scroll.scrollTop = 0;
        } catch (error) {
            let detail = error?.message || '任务执行失败。';
            if (signal.aborted) detail = native ? '已停止后续步骤。已提交的计算可能仍在后台运行。' : '任务已停止。';
            else if (error?.name === 'TimeoutError') detail = '规划请求超时，请稍后重试。';
            markStep?.('error', detail);
            for (const mark of pending.values()) mark('error', detail);
            status.textContent = detail + (completed ? ' 已完成 ' + completed + ' 步，结果保留在当前地图。' : '');
        }
    }
}
