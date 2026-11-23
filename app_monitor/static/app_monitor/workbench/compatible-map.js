/* A Canvas 2D compatibility renderer for browsers without WebGL2.
   GeoLibre remains the primary renderer. This module only handles local GeoJSON. */
async function loadLeaflet(url) {
    if (window.L) return window.L;
    await new Promise((resolve, reject) => {
        const script = document.createElement('script');
        script.src = url; script.onload = resolve; script.onerror = reject;
        document.head.append(script);
    });
    return window.L;
}

export async function createCompatibleMap(root, {leafletUrl, projectUrl}) {
    const L = await loadLeaflet(leafletUrl);
    root.replaceChildren();
    root.innerHTML = `<aside class="wb-layer-panel" aria-label="图层面板">
        <div class="wb-layer-heading"><strong>图层</strong><span id="wb-compat-count"></span><button class="wb-icon-button" type="button" title="收起图层" aria-label="收起图层"><i class="fas fa-angle-left"></i></button></div>
        <div class="wb-layer-caption">当前工程</div><div class="wb-layer-scroll"><div class="wb-layer-list"></div>
        <section class="ark-background" aria-label="背景" data-kind="vector" data-selected="false">
          <div class="ark-background-heading">
            <button type="button" class="ark-background-eye" aria-label="隐藏背景" title="隐藏背景"><i class="far fa-eye" aria-hidden="true"></i></button>
            <i class="fas fa-layer-group ark-background-symbol" aria-hidden="true"></i>
            <button type="button" class="ark-background-title" aria-expanded="false" aria-controls="ark-background-options"><span>背景</span><small>天地图</small><i class="fas fa-angle-right" aria-hidden="true"></i></button>
          </div>
          <div class="ark-background-options" id="ark-background-options" hidden>
            <fieldset><legend>底图</legend>
              <label><input type="radio" name="ark-basemap" value="vector" checked><span>电子地图<small>天地图</small></span></label>
              <label><input type="radio" name="ark-basemap" value="imagery"><span>卫星影像<small>天地图</small></span></label>
              <label><input type="radio" name="ark-basemap" value="amap"><span>高德地图<small>高德开放平台</small></span></label>
              <label><input type="radio" name="ark-basemap" value="blank"><span>不显示底图</span></label>
            </fieldset>
            <label class="ark-background-labels"><input type="checkbox" aria-label="图层注记" checked><span>图层注记</span></label>
            <p class="ark-background-note">注记随电子地图 / 卫星影像切换</p>
            <label class="ark-background-opacity"><span>透明度</span><input type="range" min="0" max="1" step="0.05" value="1" aria-label="背景透明度"><output>100%</output></label>
          </div>
        </section></div>
        <div class="wb-layer-source"><span class="wb-status-dot"></span>模拟示例 · 仅供操作演示</div>
    </aside><div class="wb-compatible-map" aria-label="兼容模式地图"></div>
    <button class="wb-layers-toggle wb-button" type="button" aria-label="展开图层"><i class="fas fa-layer-group"></i> 图层</button>
    <div class="wb-compat-note"><i class="fas fa-info-circle"></i><span>当前使用兼容地图，支持图层、导入和保存。</span><button type="button" aria-label="关闭提示">×</button></div>`;
    const list = root.querySelector('.wb-layer-list');
    const mapRoot = root.querySelector('.wb-compatible-map');
    const listeners = new Map();
    const entries = new Map();
    let project = null;
    let selected = null;
    let disposed = false;
    let backgroundKind = 'vector';
    let backgroundLabels = true;
    let backgroundVisible = true;
    let backgroundOpacity = 1;
    let basemapRequest = 0;
    const map = L.map(mapRoot, {preferCanvas: true, zoomControl: false, zoomAnimation: false,
        fadeAnimation: false, markerZoomAnimation: false}).setView([34.96, 113.58], 10);
    L.control.zoom({position: 'topright'}).addTo(map);
    L.control.scale({position: 'bottomleft', imperial: false}).addTo(map);
    const bases = L.layerGroup().addTo(map);
    const baseItems = [];
    map.createPane('compatibleBasemap');
    map.getPane('compatibleBasemap').style.zIndex = 200;
    map.getPane('compatibleBasemap').style.pointerEvents = 'none';
    function emit(type, value) { for (const fn of listeners.get(type) || []) fn(value); }
    const background = root.querySelector('.ark-background');
    const backgroundTitle = background.querySelector('.ark-background-title');
    const backgroundEye = background.querySelector('.ark-background-eye');
    const labelInput = background.querySelector('[type=checkbox]');
    const opacityInput = background.querySelector('[type=range]');
    function updateBackground() {
        background.dataset.kind = backgroundKind;
        backgroundTitle.querySelector('small').textContent = backgroundKind === 'amap' ? '高德地图' : backgroundKind === 'blank' ? '无底图' : '天地图';
        backgroundEye.setAttribute('aria-label', backgroundVisible ? '隐藏背景' : '显示背景');
        backgroundEye.title = backgroundVisible ? '隐藏背景' : '显示背景';
        backgroundEye.firstElementChild.className = `far ${backgroundVisible ? 'fa-eye' : 'fa-eye-slash'}`;
        background.querySelectorAll('[name=ark-basemap]').forEach(input => { input.checked = input.value === backgroundKind; });
        labelInput.checked = backgroundLabels;
        labelInput.disabled = !['vector', 'imagery'].includes(backgroundKind);
        background.querySelector('.ark-background-note').textContent = backgroundKind === 'amap' ? '高德底图自带注记' : backgroundKind === 'blank' ? '仅显示当前工程图层' : '注记随电子地图 / 卫星影像切换';
        opacityInput.value = backgroundOpacity;
        background.querySelector('output').textContent = Math.round(backgroundOpacity * 100) + '%';
    }
    function applyBackgroundAppearance() {
        if (backgroundVisible) { if (!map.hasLayer(bases)) bases.addTo(map); }
        else if (map.hasLayer(bases)) map.removeLayer(bases);
        baseItems.forEach(layer => layer.setOpacity(backgroundOpacity));
        updateBackground();
        emit('renderStateChanged', null);
    }
    backgroundTitle.onclick = () => {
        const open = backgroundTitle.getAttribute('aria-expanded') !== 'true';
        backgroundTitle.setAttribute('aria-expanded', String(open));
        backgroundTitle.querySelector('i').className = `fas ${open ? 'fa-angle-down' : 'fa-angle-right'}`;
        background.querySelector('.ark-background-options').hidden = !open;
        background.dataset.selected = String(open);
    };
    backgroundEye.onclick = () => { backgroundVisible = !backgroundVisible; applyBackgroundAppearance(); };
    function changeBackground() {
        backgroundVisible = true; applyBackgroundAppearance();
        emit('basemapChanged', {kind: backgroundKind, labels: backgroundLabels});
    }
    background.querySelectorAll('[name=ark-basemap]').forEach(input => {
        input.onchange = () => { backgroundKind = input.value; changeBackground(); };
    });
    labelInput.onchange = () => { backgroundLabels = labelInput.checked; changeBackground(); };
    opacityInput.oninput = () => { backgroundOpacity = Number(opacityInput.value); applyBackgroundAppearance(); };
    function viewport() {
        const center = map.getCenter();
        return {center: [center.lng, center.lat], zoom: map.getZoom(), bearing: 0, pitch: 0};
    }
    map.on('moveend', () => emit('viewChanged', viewport()));
    function collapse(value) {
        root.classList.toggle('layers-collapsed', value);
        setTimeout(() => map.invalidateSize({pan: false}), 50);
    }
    root.querySelector('.wb-layer-heading button').onclick = () => collapse(true);
    root.querySelector('.wb-layers-toggle').onclick = () => collapse(false);
    root.querySelector('.wb-compat-note button').onclick = () => root.querySelector('.wb-compat-note').remove();
    if (innerWidth < 700) collapse(true);

    function style(spec) {
        return {color: spec.style?.strokeColor || '#3f8b84', weight: spec.style?.strokeWidth ?? 2,
            opacity: (spec.style?.strokeOpacity ?? 1) * (spec.opacity ?? 1),
            fillColor: spec.style?.fillColor || '#6ca492', fillOpacity: (spec.style?.fillOpacity ?? .35) * (spec.opacity ?? 1),
            dashArray: spec.style?.strokeDash?.join(' ') || null};
    }
    function popup(feature) {
        const node = document.createElement('dl'); node.className = 'wb-map-properties';
        Object.entries(feature.properties || {}).slice(0, 12).forEach(([key, value]) => {
            const term = document.createElement('dt'); const text = document.createElement('dd');
            term.textContent = key; text.textContent = value == null ? '—' : typeof value === 'object' ? JSON.stringify(value) : String(value);
            node.append(term, text);
        });
        return node;
    }
    function add(spec) {
        if (entries.has(spec.id) || spec.type !== 'geojson' || !spec.geojson) throw new Error('Unsupported compatible layer');
        const data = structuredClone(spec);
        const layer = L.geoJSON(data.geojson, {style: feature => ({
            ...style(data),
            ...(data.style?.simpleStyleEnabled && feature?.properties?.stroke
                ? {color: feature.properties.stroke} : {}),
            ...(data.style?.simpleStyleEnabled && feature?.properties?.fill
                ? {fillColor: feature.properties.fill, fillOpacity: (feature.properties['fill-opacity'] ?? 1) * (data.opacity ?? 1)}
                : {}),
        }),
            pointToLayer: (_, latlng) => L.circleMarker(latlng, {...style(data), radius: data.style?.circleRadius || 5}),
            onEachFeature: (feature, part) => part.bindPopup(() => popup(feature), {maxWidth: 280})});
        if (data.visible !== false) layer.addTo(map);
        entries.set(data.id, {spec: data, layer});
        return data.id;
    }
    function renderRows() {
        list.replaceChildren();
        root.querySelector('#wb-compat-count').textContent = entries.size;
        [...entries.values()].reverse().forEach(({spec, layer}) => {
            const row = document.createElement('div'); row.className = 'wb-layer-row';
            row.classList.toggle('selected', selected === spec.id);
            row.dataset.layerId = spec.id;
            const line = document.createElement('div'); line.className = 'wb-layer-line';
            const visible = document.createElement('button'); visible.type = 'button'; visible.className = 'wb-layer-visibility';
            visible.setAttribute('aria-label', (spec.visible !== false ? '隐藏' : '显示') + spec.name);
            visible.innerHTML = `<i class="far ${spec.visible !== false ? 'fa-eye' : 'fa-eye-slash'}" aria-hidden="true"></i>`;
            visible.onclick = () => {
                spec.visible = spec.visible === false;
                spec.visible ? layer.addTo(map) : map.removeLayer(layer);
                renderRows(); emit('featuresChanged', {layerId: spec.id});
            };
            const symbol = document.createElement('span'); symbol.className = 'wb-layer-symbol';
            const kind = spec.geojson.features[0]?.geometry?.type || '';
            symbol.dataset.kind = kind;
            symbol.style.setProperty('--layer-color', kind.includes('Line') ? spec.style?.strokeColor || '#548e92' : spec.style?.fillColor || '#6ca492');
            const name = document.createElement('button'); name.type = 'button'; name.className = 'wb-layer-name'; name.textContent = spec.name;
            name.onclick = () => { selected = selected === spec.id ? null : spec.id; renderRows(); };
            const focus = document.createElement('button'); focus.type = 'button'; focus.className = 'wb-layer-visibility'; focus.setAttribute('aria-label', '定位' + spec.name);
            focus.innerHTML = '<i class="fas fa-crosshairs" aria-hidden="true"></i>';
            focus.onclick = () => { if (layer.getBounds().isValid()) map.fitBounds(layer.getBounds(), {padding: [40, 40], maxZoom: 14}); };
            line.append(visible, symbol, name, focus); row.append(line);
            const meta = document.createElement('div'); meta.className = 'wb-layer-meta'; meta.textContent = `矢量图层 · ${spec.geojson.features.length} 个要素`; row.append(meta);
            if (selected === spec.id) {
                const controls = document.createElement('div'); controls.className = 'wb-layer-properties';
                const label = document.createElement('label'); label.textContent = '透明度';
                const range = document.createElement('input'); range.type = 'range'; range.min = 0; range.max = 1; range.step = .05; range.value = spec.opacity ?? 1; range.setAttribute('aria-label', spec.name + '透明度');
                const output = document.createElement('output'); output.textContent = Math.round(range.value * 100) + '%';
                range.oninput = () => { spec.opacity = Number(range.value); layer.setStyle(style(spec)); output.textContent = Math.round(range.value * 100) + '%'; };
                controls.append(label, range, output); row.append(controls);
            }
            list.append(row);
        });
    }
    const client = {
        async loadProject(url) {
            const response = await fetch(url);
            if (!response.ok) throw new Error('Could not load project');
            await client.openProject(await response.json(), url);
        },
        async openProject(next, url = null) {
            if (!Array.isArray(next.layers) || next.layers.some(layer => layer.type !== 'geojson' || !Array.isArray(layer.geojson?.features))) throw new Error('Unsupported project');
            for (const entry of entries.values()) map.removeLayer(entry.layer);
            entries.clear(); project = next; selected = null;
            backgroundVisible = next.basemapVisible !== false;
            backgroundOpacity = typeof next.basemapOpacity === 'number' ? Math.max(0, Math.min(1, next.basemapOpacity)) : 1;
            applyBackgroundAppearance();
            next.layers.forEach(add); renderRows(); emit('projectLoaded', {name: next.name, url});
        },
        async addLayer(spec) { const id = add(spec); selected = id; renderRows(); emit('featuresChanged', {layerId: id}); return id; },
        async listLayers() { return [...entries.values()].map(({spec}) => ({id: spec.id, name: spec.name, type: spec.type, visible: spec.visible !== false, opacity: spec.opacity ?? 1})); },
        describeAnalysisLayer(id) {
            const geometry = new Set(), numericFields = new Set();
            for (const f of entries.get(id)?.spec.geojson.features || []) {
                if (f.geometry?.type) geometry.add(f.geometry.type);
                for (const [name, value] of Object.entries(f.properties || {})) {
                    if (Number.isFinite(value) && numericFields.size < 24) numericFields.add(name);
                }
            }
            return {geometry: [...geometry], numericFields: [...numericFields]};
        },
        async setLayerVisibility(id, visible) {
            const entry = entries.get(id);
            if (!entry) throw new Error('图层已移除。');
            entry.spec.visible = visible;
            if (visible) entry.layer.addTo(map);
            else map.removeLayer(entry.layer);
            renderRows();
        },
        async getLayerFeatures(id) { return entries.get(id)?.spec.geojson.features || []; },
        async getViewport() { return viewport(); },
        async setBasemap(url) {
            const ticket = ++basemapRequest;
            const response = await fetch(url);
            if (!response.ok) throw new Error('Basemap unavailable');
            const style = await response.json();
            if (disposed || ticket !== basemapRequest) return;
            const params = new URL(url, location.href).searchParams;
            backgroundKind = params.get('kind') || 'vector'; backgroundLabels = params.get('labels') !== '0';
            bases.clearLayers(); baseItems.length = 0;
            let index = 0;
            for (const source of Object.values(style.sources)) {
                let layer;
                if (source.type === 'raster') {
                    const template = source.tiles[0].replace('t0.tianditu', 't{s}.tianditu');
                    layer = L.tileLayer(template, {subdomains: '01234567', maxZoom: 18, crossOrigin: 'anonymous', attribution: source.attribution, zIndex: index++});
                    for (const type of ['loading', 'load', 'tileerror']) layer.on(type, () => emit('renderStateChanged', null));
                } else if (source.type === 'image') {
                    const north = Math.max(...source.coordinates.map(c => c[1]));
                    const south = Math.min(...source.coordinates.map(c => c[1]));
                    const west = Math.min(...source.coordinates.map(c => c[0]));
                    const east = Math.max(...source.coordinates.map(c => c[0]));
                    layer = L.imageOverlay(source.url, [[south, west], [north, east]], {pane: 'compatibleBasemap', className: 'ark-basemap-image', crossOrigin: 'anonymous', attribution: style.metadata?.arkAttribution || ''});
                    layer.on('load error', () => emit('renderStateChanged', null));
                }
                if (layer) {
                    layer.addTo(bases); baseItems.push(layer);
                }
            }
            if (project) project.basemapStyleUrl = url;
            applyBackgroundAppearance();
        },
        async setView(view) {
            if (view.bbox) map.fitBounds([[view.bbox[1], view.bbox[0]], [view.bbox[3], view.bbox[2]]], {padding: [36, 36], animate: false});
            else map.setView([view.center[1], view.center[0]], view.zoom || map.getZoom(), {animate: false});
        },
        renderState() {
            if (!backgroundVisible) return 'ready';
            if (baseItems.some(layer => layer.getElement?.()?.complete && !layer.getElement().naturalWidth)) return 'error';
            return baseItems.some(layer => layer.isLoading?.() || (layer.getElement && !layer.getElement().complete)) ? 'loading' : 'ready';
        },
        async exportImage() {
            const canvas = document.createElement('canvas'); const bounds = mapRoot.getBoundingClientRect();
            canvas.width = Math.round(bounds.width); canvas.height = Math.round(bounds.height);
            const ctx = canvas.getContext('2d'); ctx.fillStyle = '#f5f7f3'; ctx.fillRect(0, 0, canvas.width, canvas.height);
            for (const source of mapRoot.querySelectorAll('.leaflet-tile-pane img, img.ark-basemap-image, .leaflet-overlay-pane canvas')) {
                if (source instanceof HTMLImageElement && (!source.complete || !source.naturalWidth)) continue;
                const box = source.getBoundingClientRect();
                ctx.globalAlpha = source instanceof HTMLImageElement ? backgroundOpacity : 1;
                ctx.drawImage(source, box.left - bounds.left, box.top - bounds.top, box.width, box.height);
            }
            ctx.globalAlpha = 1;
            ctx.font = '12px Microsoft YaHei, sans-serif';
            ctx.fillStyle = '#fff'; ctx.fillRect(0, canvas.height - 27, canvas.width, 27);
            ctx.fillStyle = '#546c65'; ctx.fillText('方舟科研地图 · 示例 / 本地数据', 12, canvas.height - 10);
            const credit = backgroundKind === 'blank' ? '' : backgroundKind === 'amap' ? '© 高德地图' : '© 天地图';
            if (canvas.width > 600) ctx.fillText(credit, canvas.width - ctx.measureText(credit).width - 12, canvas.height - 10);
            else { ctx.font = '9px sans-serif'; ctx.fillText(credit, canvas.width - ctx.measureText(credit).width - 8, canvas.height - 10); }
            return canvas.toDataURL('image/png');
        },
        async saveProject() {
            const snapshot = {...project, basemapVisible: backgroundVisible, basemapOpacity: backgroundOpacity,
                mapView: viewport(), layers: [...entries.values()].map(entry => entry.spec)};
            const blob = new Blob([JSON.stringify(snapshot, null, 2)], {type: 'application/json'});
            const url = URL.createObjectURL(blob); const link = document.createElement('a'); link.href = url; link.download = '方舟科研工程.geolibre.json'; link.click();
            setTimeout(() => URL.revokeObjectURL(url), 1000);
        },
        on(type, listener) { if (!listeners.has(type)) listeners.set(type, new Set()); listeners.get(type).add(listener); return () => listeners.get(type)?.delete(listener); },
        disconnect() { if (disposed) return; disposed = true; listeners.clear(); map.remove(); root.replaceChildren(); },
    };
    await client.loadProject(projectUrl);
    map.invalidateSize();
    return client;
}
