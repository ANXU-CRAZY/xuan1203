import {connect} from './geolibre-embed.js';
import {initAgent} from './agent.js?v=11';

const appsToggle = document.getElementById('wb-apps-toggle');
const appsMenu = document.getElementById('wb-apps-menu');
function closeApps() {
    appsMenu.hidden = true;
    appsToggle.setAttribute('aria-expanded', 'false');
}
appsToggle.addEventListener('click', () => {
    const opening = appsMenu.hidden;
    appsMenu.hidden = !opening;
    appsToggle.setAttribute('aria-expanded', String(opening));
});
document.addEventListener('click', event => {
    if (!appsMenu.hidden && !appsMenu.contains(event.target) && !appsToggle.contains(event.target)) closeApps();
});
document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && !appsMenu.hidden) { closeApps(); appsToggle.focus(); }
});

const workspace = document.getElementById('wb-workspace');
const frame = document.getElementById('wb-map');
const loading = document.getElementById('wb-loading');
const guide = document.getElementById('wb-guide');
const help = document.getElementById('wb-help');
const status = document.getElementById('wb-status');
const fileInput = document.getElementById('wb-file');
const exportButton = document.getElementById('wb-export');
const exportDialog = document.getElementById('wb-export-dialog');
const exportProgress = document.getElementById('wb-export-progress');
const projectUrl = new URL(workspace.dataset.projectUrl, location.href).href;
const region = {bbox: [113.25, 34.89, 113.9, 35.045]};
let client;
let toastTimer;
let renderObserver;
let compatible = false;
let boot = 0;
let mapVersion = 0;
let basemap = 'vector';
let annotations = true;
let basemapSignature = '';
let basemapTimer;

function toast(message) {
    const node = document.getElementById('wb-toast');
    node.textContent = message;
    node.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { node.hidden = true; }, 4500);
}

function showGuide(open) {
    guide.hidden = !open;
    help.setAttribute('aria-expanded', String(open));
    if (open) document.getElementById('wb-guide-close').focus();
    else {
        try { sessionStorage.setItem('ark-workbench-guide-seen', '1'); } catch { /* Optional preference. */ }
        help.focus();
    }
}
help.addEventListener('click', () => showGuide(guide.hidden));
document.getElementById('wb-guide-close').addEventListener('click', () => showGuide(false));
document.getElementById('wb-start').addEventListener('click', () => showGuide(false));
document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && !guide.hidden) showGuide(false);
});

function setStatus(text) {
    status.replaceChildren();
    const dot = document.createElement('span');
    dot.className = 'wb-status-dot';
    status.append(dot, document.createTextNode(text));
}

function updateViewport(view) {
    if (view.center?.length === 2) document.getElementById('wb-coordinates').textContent = `${view.center[0].toFixed(3)}° E, ${view.center[1].toFixed(3)}° N`;
    if (basemap === 'amap') { clearTimeout(basemapTimer); basemapTimer = setTimeout(updateBasemap, 650); }
}

async function updateLayers() {
    if (!client) return;
    try {
        const layers = await client.listLayers();
        document.getElementById('wb-layer-count').textContent = `${layers.length} 个图层`;
    } catch { /* A reload will reset the connection and show the loading state. */ }
}

async function action(button, task) {
    if (!client || button.disabled) return;
    button.disabled = true;
    button.dataset.busy = 'true';
    try { await task(); }
    catch (error) {
        toast(/render|tiles|timed out|timeout/i.test(error?.message || '')
            ? '地图仍在加载，请稍等片刻再试。' : '操作未完成，请稍后重试。');
    }
    finally {
        delete button.dataset.busy;
        button.disabled = false;
        updateExportState();
    }
}

function renderState() {
    try { return compatible ? client.renderState() : frame.contentDocument?.documentElement.dataset.geolibreLoadState; }
    catch { return 'error'; }
}

function updateExportState() {
    if (!client) return;
    const state = renderState();
    exportButton.title = state === 'ready' ? '导出当前地图' : '选择导出方式';
    setStatus(state === 'ready' ? '地图就绪 · 可导出' :
        state === 'error' ? '地图可操作 · 部分图层加载失败' : '地图可操作 · 正在渲染');
}

function requestEditor(type, payload = {}) {
    return new Promise((resolve, reject) => {
        const target = frame.contentWindow;
        const id = crypto.randomUUID();
        const finish = (callback, value) => {
            clearTimeout(timer);
            window.removeEventListener('message', receive);
            callback(value);
        };
        const receive = event => {
            if (event.source !== target || event.origin !== location.origin ||
                event.data?.source !== 'ark-workbench-map' || event.data.type !== 'workbench-result' ||
                event.data.id !== id) return;
            if (event.data.error) finish(reject, new Error(event.data.error));
            else finish(resolve, event.data.value);
        };
        const timer = setTimeout(() => finish(reject, new Error('地图未响应，请重试。')), 40000);
        window.addEventListener('message', receive);
        target.postMessage({source: 'ark-workbench', id, type, ...payload}, location.origin);
    });
}

function changeBasemap(choice) {
    if (!choice || !['vector', 'imagery', 'amap', 'blank'].includes(choice.kind) || typeof choice.labels !== 'boolean') return;
    reflectBasemap(choice);
    basemapSignature = '';
    return updateBasemap();
}
function reflectBasemap(choice) {
    basemap = choice.kind;
    annotations = choice.labels;
    const credit = document.getElementById('wb-map-credit');
    credit.textContent = ['blank', 'external'].includes(basemap) ? '' : basemap === 'amap' ? '© 高德地图' : '© 天地图';
    frame.contentDocument?.documentElement.toggleAttribute('data-ark-map-credit', Boolean(credit.textContent));
    if (basemap === 'external') clearTimeout(basemapTimer);
}
window.addEventListener('message', event => {
    if (compatible || event.source !== frame.contentWindow || event.origin !== location.origin || event.data?.source !== 'ark-workbench-map') return;
    if (event.data.type === 'print-layout') workspace.classList.toggle('wb-print-layout-open', event.data.open === true);
    else if (client && event.data.type === 'basemap-change') changeBasemap(event.data);
    else if (event.data.type === 'basemap-state' && ['vector', 'imagery', 'amap', 'blank', 'external'].includes(event.data.kind) &&
        typeof event.data.labels === 'boolean') reflectBasemap(event.data);
});

async function updateBasemap(strict = false) {
    if (!client || basemap === 'external') return;
    try {
        const view = await client.getViewport();
        const mapCanvas = compatible ? document.querySelector('.wb-compatible-map') : frame.contentDocument?.querySelector('.maplibregl-canvas');
        const size = mapCanvas?.getBoundingClientRect() || frame.getBoundingClientRect();
        const url = new URL('basemap.json', new URL(workspace.dataset.engineUrl, location.href));
        url.search = new URLSearchParams({kind: basemap, labels: annotations ? '1' : '0',
            // MapLibre uses a 512px world tile; Leaflet and AMap use 256px.
            lng: view.center[0].toFixed(5), lat: view.center[1].toFixed(5), zoom: (view.zoom + (compatible ? 0 : 1)).toFixed(2),
            width: Math.max(1, Math.round(size.width)), height: Math.max(1, Math.round(size.height))});
        const signature = basemap === 'amap' ? url.href : `${basemap}-${annotations}`;
        if (signature === basemapSignature) return;
        basemapSignature = signature;
        if (compatible) await client.setBasemap(url.href);
        else if (strict) {
            // Resolve only once the iframe has applied the chosen provider URL.
            await new Promise((resolve, reject) => {
                const receive = event => {
                    if (event.origin !== location.origin || event.source !== frame.contentWindow ||
                        event.data?.source !== 'ark-workbench-map' || event.data?.type !== 'basemap-applied' ||
                        event.data?.url !== url.href) return;
                    clearTimeout(timer);
                    window.removeEventListener('message', receive);
                    resolve();
                };
                const timer = setTimeout(() => {
                    window.removeEventListener('message', receive);
                    reject(new Error('地图未确认底图切换。'));
                }, 4000);
                window.addEventListener('message', receive);
                frame.contentWindow.postMessage({source: 'ark-workbench', type: 'basemap', url: url.href, acknowledge: true}, location.origin);
            });
        } else frame.contentWindow.postMessage({source: 'ark-workbench', type: 'basemap', url: url.href}, location.origin);
        updateExportState();
    } catch {
        basemapSignature = '';
        const text = '底图暂未加载，请检查地图配置或切换其他底图。';
        if (strict) throw new Error(text);
        toast(text);
    }
}

document.getElementById('wb-save').addEventListener('click', event => action(event.currentTarget, async () => {
    if (compatible) {
        await client.saveProject();
        toast('工程已交给浏览器下载。');
        return;
    }
    const {content, name, localRasters} = await requestEditor('save-project');
    const url = URL.createObjectURL(new Blob([content], {type: 'application/json'}));
    const link = document.createElement('a');
    link.href = url;
    link.download = (name || 'ARK GeoStudio').replace(/[<>:"/\\|?*]/g, '_') + '.geolibre';
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    toast(localRasters ? `工程已下载。另有 ${localRasters} 个本地栅格需单独保存，重开工程后可重新导入。` :
        '工程已交给浏览器下载，可通过「导入数据」重开。');
}));

document.getElementById('wb-home').addEventListener('click', event => action(event.currentTarget, () => client.setView(region)));
document.getElementById('wb-sample').addEventListener('click', event => action(event.currentTarget, async () => {
    if (!window.confirm('重新打开示例工程会替换当前图层。请先通过“项目”菜单保存需要保留的内容。')) return;
    await client.loadProject(projectUrl);
    await client.setView(region);
    basemapSignature = ''; await updateBasemap();
    document.title = '方舟云图 · 智「绘」一切';
    await updateLayers();
    toast('已打开示例工程');
}));

async function exportMap(signal, visibleOnly = false) {
    let image = visibleOnly && !compatible ? await requestEditor('capture-visible') : await client.exportImage();
    signal?.throwIfAborted();
    if (typeof image !== 'string' || !image.startsWith('data:image/')) throw new Error('Invalid image');
    if (!compatible) {
        const source = new Image(); source.src = image; await source.decode();
        const canvas = document.createElement('canvas'); canvas.width = source.width; canvas.height = source.height;
        const ctx = canvas.getContext('2d'); ctx.drawImage(source, 0, 0);
        ctx.fillStyle = '#ffffffee'; ctx.fillRect(0, canvas.height-26, canvas.width, 26);
        ctx.font = '11px Microsoft YaHei, sans-serif'; ctx.fillStyle = '#4f6c60';
        const credit = basemap === 'amap' ? '© 高德地图' : ['blank', 'external'].includes(basemap) ? '' : '© 天地图';
        ctx.fillText('ARK GeoStudio', 12, canvas.height-9);
        ctx.fillText(credit, canvas.width-ctx.measureText(credit).width-12, canvas.height-9);
        image = canvas.toDataURL('image/png');
    }
    const link = document.createElement('a');
    link.href = image;
    link.download = visibleOnly ? 'ARK GeoStudio-当前画面.png' : 'ARK GeoStudio-地图.png';
    signal?.throwIfAborted();
    link.click();
    toast('地图图片已导出');
}
exportButton.addEventListener('click', () => {
    if (renderState() === 'ready') return action(exportButton, () => exportMap());
    exportProgress.textContent = '';
    exportDialog.showModal();
});
document.getElementById('wb-export-visible').addEventListener('click', () => {
    exportDialog.close();
    action(exportButton, () => exportMap(undefined, true));
});
const waitExportButton = document.getElementById('wb-export-wait');
waitExportButton.addEventListener('click', async () => {
    waitExportButton.disabled = true;
    exportProgress.textContent = '正在等待完整地图…';
    try {
        const deadline = performance.now() + 8000;
        while (exportDialog.open && renderState() !== 'ready' && performance.now() < deadline) {
            await new Promise(resolve => setTimeout(resolve, 160));
        }
        if (!exportDialog.open) return;
        if (renderState() !== 'ready') {
            exportProgress.textContent = '地图仍未完成渲染。可继续等待，或下载当前画面。';
            return;
        }
        exportDialog.close();
        await action(exportButton, () => exportMap());
    } finally {
        waitExportButton.disabled = false;
    }
});

document.getElementById('wb-import').addEventListener('click', () => fileInput.click());
fileInput.addEventListener('change', async () => {
    const file = fileInput.files[0];
    fileInput.value = '';
    if (!file || !client) return;
    if (file.size > 20 * 1024 * 1024) { toast('请选择小于 20 MB 的工程或 GeoJSON 文件。'); return; }
    await action(document.getElementById('wb-import'), async () => {
        const content = await file.text();
        let data;
        try { data = JSON.parse(content.replace(/^\uFEFF/, '')); }
        catch { toast('文件无法读取，请检查工程或 GeoJSON 文件格式。'); return; }
        if (/\.geolibre$/i.test(file.name) || Array.isArray(data?.layers) && data?.mapView) {
            if (!window.confirm('打开工程会替换当前图层。请先保存需要保留的内容。')) return;
            try {
                if (compatible) {
                    await client.openProject(data);
                    await client.setView(data.mapView);
                    const url = new URL(data.basemapStyleUrl || '', location.href);
                    const kind = url.searchParams.get('kind') || 'vector';
                    await changeBasemap({kind, labels: url.searchParams.get('labels') !== '0'});
                } else {
                    await requestEditor('open-project', {content: content.replace(/^\uFEFF/, '')});
                }
                await updateLayers();
                toast('已打开工程：' + (data.name || file.name));
            } catch {
                toast('无法打开工程，请检查文件格式及当前地图支持的图层类型。');
            }
            return;
        }
        if (data?.type === 'Feature') data = {type: 'FeatureCollection', features: [data]};
        if (data?.type !== 'FeatureCollection' || !Array.isArray(data.features) || !data.features.length ||
            data.features.some(feature => feature?.type !== 'Feature' || !feature.geometry || !Object.hasOwn(feature.geometry, 'type'))) {
            toast('请选择包含有效地理要素的 GeoJSON 文件。'); return;
        }
        const bounds = [Infinity, Infinity, -Infinity, -Infinity];
        function coordinates(value) {
            if (!Array.isArray(value) || !value.length) throw new Error('Invalid coordinates');
            if (typeof value[0] === 'number') {
                const [x, y] = value;
                if (!Number.isFinite(x) || !Number.isFinite(y) || Math.abs(x) > 180 || Math.abs(y) > 90) throw new Error('Invalid coordinates');
                bounds[0] = Math.min(bounds[0], x); bounds[1] = Math.min(bounds[1], y);
                bounds[2] = Math.max(bounds[2], x); bounds[3] = Math.max(bounds[3], y);
            } else value.forEach(coordinates);
        }
        function geometry(value) {
            if (value?.type === 'GeometryCollection' && Array.isArray(value.geometries)) value.geometries.forEach(geometry);
            else if (['Point', 'MultiPoint', 'LineString', 'MultiLineString', 'Polygon', 'MultiPolygon'].includes(value?.type)) coordinates(value.coordinates);
            else throw new Error('Invalid geometry');
        }
        try { data.features.forEach(feature => geometry(feature.geometry)); }
        catch { toast('快捷导入需要有效的 WGS84 经纬度坐标；其他坐标系请使用地图内“添加数据”菜单。'); return; }
        if (!bounds.every(Number.isFinite)) { toast('文件中没有可显示的地理坐标。'); return; }
        const id = `local-${crypto.randomUUID()}`;
        const name = file.name.replace(/\.(geojson|json)$/i, '');
        await client.addLayer({id, name, type: 'geojson', source: {type: 'geojson'}, geojson: data,
            style: {fillColor: '#72a48b', fillOpacity: 0.3, strokeColor: '#248e99', strokeWidth: 2, circleRadius: 6},
            metadata: {origin: 'local-file', fileName: file.name}});
        document.title = `${file.name} · 方舟云图`;
        await client.setView(bounds[0] === bounds[2] && bounds[1] === bounds[3]
            ? {center: bounds.slice(0, 2), zoom: 13}
            : {bbox: bounds});
        await updateLayers();
        toast(`已导入 ${data.features.length} 个要素，文件未上传`);
    });
});

function webglAvailable() {
    try {
        const canvas = document.createElement('canvas');
        const gl = canvas.getContext('webgl2');
        if (!gl) return false;
        gl.getExtension('WEBGL_lose_context')?.loseContext();
        return true;
    } catch { return false; }
}

async function finishReady() {
    document.querySelectorAll('[data-needs-map]').forEach(button => { button.disabled = false; });
    client.on('viewChanged', updateViewport);
    client.on('projectLoaded', () => { mapVersion++; updateLayers(); });
    client.on('featuresChanged', updateLayers);
    if (compatible) {
        client.on('renderStateChanged', updateExportState);
        client.on('basemapChanged', changeBasemap);
    }
    await updateLayers();
    await client.setView(region);
    updateViewport(await client.getViewport());
    reflectBasemap({kind: basemap, labels: annotations});
    basemapSignature = ''; await updateBasemap();
    if (!compatible) {
        renderObserver = new MutationObserver(updateExportState);
        renderObserver.observe(frame.contentDocument.documentElement, {attributes: true, attributeFilter: ['data-geolibre-load-state']});
    }
    loading.hidden = true;
    updateExportState();
}

async function startCompatible(ticket) {
    const {createCompatibleMap} = await import('./compatible-map.js?v=20261115-agent2');
    if (ticket !== boot) return;
    compatible = true;
    frame.hidden = true; frame.src = 'about:blank';
    const host = document.getElementById('wb-compatible'); host.hidden = false;
    client = await createCompatibleMap(host, {leafletUrl: workspace.dataset.leafletUrl, projectUrl});
    workspace.dataset.renderer = 'compatible';
    document.getElementById('wb-mode').textContent = '兼容地图';
    await finishReady();
}

async function start() {
    const ticket = ++boot;
    workspace.classList.remove('wb-print-layout-open');
    document.querySelectorAll('[data-needs-map]').forEach(button => { button.disabled = true; });
    client?.disconnect();
    renderObserver?.disconnect();
    client = null;
    compatible = false;
    clearTimeout(basemapTimer);
    loading.hidden = false;
    loading.classList.remove('is-compact');
    document.getElementById('wb-retry').hidden = true;
    document.getElementById('wb-loading-title').textContent = '正在准备科研地图';
    document.getElementById('wb-loading-copy').textContent = '加载地图组件与示例工程，请稍候';
    setStatus('正在加载');
    const compact = setTimeout(() => { if (ticket === boot && !client) loading.classList.add('is-compact'); }, 2200);
    if (!webglAvailable()) {
        try { await startCompatible(ticket); }
        catch { showFailure(); }
        clearTimeout(compact);
        return;
    }
    document.getElementById('wb-compatible').hidden = true;
    frame.hidden = false;
    const ready = connect(frame, {origin: location.origin, timeoutMs: 16000, requestTimeoutMs: 40000});
    const url = new URL(workspace.dataset.engineUrl, location.href);
    url.search = new URLSearchParams({url: projectUrl, settingsUrl: new URL(workspace.dataset.settingsUrl, location.href).href,
        locale: 'zh', theme: 'light', welcome: '0', loading: 'true'});
    frame.src = url.href;
    try {
        client = await ready;
        workspace.dataset.renderer = 'geolibre';
        document.getElementById('wb-mode').textContent = 'GeoAI-Studio';
        await finishReady();
    } catch {
        client?.disconnect(); client = null;
        try { await startCompatible(ticket); }
        catch { showFailure(); }
    } finally { clearTimeout(compact); }
}

function showFailure() {
        loading.hidden = false;
        document.querySelectorAll('[data-needs-map]').forEach(button => { button.disabled = true; });
        document.getElementById('wb-loading-title').textContent = '地图暂时未能打开';
        document.getElementById('wb-loading-copy').textContent = '请检查本地服务与网络连接，然后重新加载。';
        document.getElementById('wb-retry').hidden = false;
        setStatus('等待重新加载');
}
document.getElementById('wb-retry').addEventListener('click', start);
window.addEventListener('pagehide', () => { client?.disconnect(); renderObserver?.disconnect(); });
initAgent({
    getClient: () => client,
    getNativeFrame: () => compatible ? null : frame,
    getMapVersion: () => mapVersion,
    region,
    geometryUrl: new URL('ark-agent-geometry.js?v=4', new URL(workspace.dataset.engineUrl, location.href)),
    async setBasemap(kind) {
        reflectBasemap({kind, labels: annotations});
        basemapSignature = '';
        await updateBasemap(true);
    },
    async exportMap(signal) {
        const deadline = performance.now() + 15000;
        // Wait for the renderer to start processing the last camera or layer update.
        await new Promise(resolve => setTimeout(resolve, 200));
        while (renderState() !== 'ready') {
            signal.throwIfAborted();
            if (performance.now() >= deadline) throw new Error('底图或图层尚未加载完成，暂时无法导出。');
            await new Promise(resolve => setTimeout(resolve, 150));
        }
        await exportMap(signal);
    },
    refreshLayers: updateLayers,
});
start();
