/* Incremental 2D monitoring integration; Leaflet, charts and the original
 * detail modal/AI assistant remain owned by index.html. */
function installMonitoringDashboard(app) {
    const $id = id => document.getElementById(id);
    const filterKey = () => JSON.stringify([app.protectionFilter, $id('d-start').value, $id('d-end').value]);
    const original = {};
    ['init', 'openDetailModal', 'closeDetailModal', 'clearHeatmap', 'toggleHeatSelection', 'renderRealTimeLogs'].forEach(name => original[name] = app[name]);
    Object.assign(app, {
        timeline: { playing: false, years: [], token: 0, timer: null },
        bufferAnalysis: { active: false, picking: false, center: null, layer: L.layerGroup(), seq: 0, controller: null, payload: null, params: null },
        mapClusters: [], pointPage: [], _recentRecords: [], _mapController: null,
        _heatSeq: 0,

        init: function() {
            // Let the monitoring loader own the first map request. The legacy
            // species loader still fills species metadata, but must not start
            // a second request before the date range is ready.
            this._monitoringInstalled = true;
            original.init.call(this);
            this.map.createPane('monitorHitPane');
            this.map.getPane('monitorHitPane').style.zIndex = 640;
            this.map.getPane('monitorHitPane').style.pointerEvents = 'none';
            this.hitLayer = L.layerGroup().addTo(this.map);
            // Preview points, clusters, and records must share hit testing.
            // An empty upper Canvas still intercepts the lower Canvas's events.
            this.clusterRenderer = this.recordRenderer;
            this.bufferAnalysis.layer.addTo(this.map);
            this.map.on('click', event => {
                const state = this.bufferAnalysis;
                if (!state.active || !state.picking || this.heatmap.active) return;
                this.invalidateBuffer();
                state.center = event.latlng;
                state.picking = false;
                document.body.classList.remove('analysis-selecting');
                this.drawBufferPreview();
                $id('analysis-status').textContent = `中心：${event.latlng.lng.toFixed(5)}，${event.latlng.lat.toFixed(5)}。点击“运行分析”。`;
            });
            this.map.on('overlayremove overlayadd', () => {
                $id('thematic-legend').hidden = !this.map.hasLayer(this.layers.record);
                this.layoutMonitoring();
            });
            ['d-start', 'd-end'].forEach(id => $id(id).addEventListener('change', () => {
                this.pauseTimeline(); this.invalidateBuffer(); this.closeDetailModal(); this.loadMapObservations();
            }));
            $id('buffer-radius').addEventListener('input', () => { this.invalidateBuffer(); this.drawBufferPreview(); });
            $id('timeline-year')?.addEventListener('change', () => this.selectMonitoringYear());
            window.addEventListener('resize', () => this.layoutMonitoring());
            document.addEventListener('visibilitychange', () => { if (document.hidden) this.pauseTimeline(); });
            const observer = new ResizeObserver(() => this.layoutMonitoring());
            observer.observe($id('filter-bar'));
            observer.observe(document.querySelector('.top-beam'));
            const layerObserver = new MutationObserver(() => {
                const open = this.layerControl.getContainer().classList.contains('leaflet-control-layers-expanded');
                document.body.classList.toggle('layers-expanded', innerWidth <= 768 && open);
                const toggle = this.layerControl.getContainer().querySelector('.leaflet-control-layers-toggle');
                toggle.setAttribute('aria-expanded', String(open));
                toggle.setAttribute('aria-label', open ? '收起地图图层' : '展开地图图层');
                this.layoutMonitoring();
            });
            layerObserver.observe(this.layerControl.getContainer(), { attributes:true, attributeFilter:['class'] });
            // Mobile uses the same rectangular heat selection as the mouse.
            const container = this.map.getContainer();
            const latlng = e => this.map.mouseEventToLatLng(e);
            container.addEventListener('pointerdown', e => {
                if (e.pointerType !== 'touch' || !this.heatmap.active) return;
                e.preventDefault(); this.map.dragging.disable();
                this.map.fire('mousedown', { latlng: latlng(e) });
                container.setPointerCapture(e.pointerId);
            });
            container.addEventListener('pointermove', e => {
                if (e.pointerType === 'touch' && this.heatmap.start) this.map.fire('mousemove', { latlng: latlng(e) });
            });
            container.addEventListener('pointerup', e => {
                if (e.pointerType === 'touch' && this.heatmap.start) this.map.fire('mouseup', { latlng: latlng(e) });
            });
            container.addEventListener('pointercancel', () => this.toggleHeatSelection(false));
            this.loadMonitoringYears();
            this.layoutMonitoring();
        },

        layoutMonitoring: function() {
            const mobile = innerWidth <= 768;
            const compact = innerWidth <= 1024;
            if (compact && !this._compactLayout) this.layerControl?.collapse();
            this._compactLayout = compact;
            document.body.classList.toggle('layers-expanded', mobile && this.layerControl?.getContainer().classList.contains('leaflet-control-layers-expanded'));
            const beam = document.querySelector('.top-beam').getBoundingClientRect();
            document.documentElement.style.setProperty('--monitor-filter-top', `${beam.bottom + 8}px`);
            const bar = $id('filter-bar').getBoundingClientRect();
            const bottom = document.querySelector('.bottom-stats-bar').getBoundingClientRect();
            const rankElement = $id('rank-panel');
            let rank = rankElement.getBoundingClientRect();
            const layerControl = this.layerControl.getContainer();
            const layerTop = layerControl.getBoundingClientRect().top;
            const zoom = this.map.getContainer().querySelector('.leaflet-control-zoom');
            const zoomHeight = zoom ? zoom.getBoundingClientRect().height : 0;
            const zoomSpace = zoomHeight ? zoomHeight + 18 : 0;
            const layerList = layerControl.querySelector('.leaflet-control-layers-list');
            if (!mobile && layerControl.classList.contains('leaflet-control-layers-expanded') &&
                rank.height && (!rankElement.style.top || rankElement.style.top === 'auto')) {
                const naturalHeight = layerList.scrollHeight + layerControl.getBoundingClientRect().height - layerList.clientHeight;
                const liveHeight = Math.max(110, rank.bottom - layerTop - naturalHeight - zoomSpace - 20);
                document.documentElement.style.setProperty('--map-live-max-height', liveHeight + 'px');
            } else {
                document.documentElement.style.removeProperty('--map-live-max-height');
            }
            rank = rankElement.getBoundingClientRect();
            const layerBottom = rank.height && rank.top > layerTop ? Math.min(rank.top - 10, bottom.top - 10) : bottom.top - 10;
            layerControl.style.setProperty('--map-layer-list-height', Math.max(44, layerBottom - layerTop - 24 - zoomSpace) + 'px');
            const expanded = document.body.classList.contains('tools-open') || this.bufferAnalysis.active;
            const lowerEdge = mobile && !expanded ? Math.min(rank.top - 8, bottom.top - 8) : bottom.top - 8;
            document.documentElement.style.setProperty('--monitor-sidebar-top', `${bar.bottom + 8}px`);
            document.documentElement.style.setProperty('--monitor-sidebar-bottom', `${Math.max(8, innerHeight - lowerEdge)}px`);
            document.documentElement.style.setProperty('--point-pagination-bottom', `${innerHeight - bottom.top + 8}px`);
        },

        toggleMonitoringTools: function(force) {
            const show = typeof force === 'boolean' ? force : !document.body.classList.contains('tools-open');
            document.body.classList.toggle('tools-open', show);
            $id('monitor-tools-toggle')?.setAttribute('aria-expanded', String(show));
            if (!show) { this.toggleBufferAnalysis(false); this.toggleHeatSelection(false); }
            this.layoutMonitoring();
        },

        loadMonitoringYears: async function() {
            const seq = this._yearsSeq = (this._yearsSeq || 0) + 1;
            try {
                const response = await fetch(`/api/monitoring/years/?protection=${encodeURIComponent(this.protectionFilter)}`);
                if (!response.ok) throw new Error('可用年份加载失败');
                const payload = await response.json();
                if (seq !== this._yearsSeq) return;
                this.timeline.years = payload.years || [];
                if (this.timeline.years.length && !$id('d-start').value && !$id('d-end').value) {
                    $id('d-start').value = `${this.timeline.years[0]}-01-01`;
                    $id('d-end').value = `${this.timeline.years.at(-1)}-12-31`;
                    this.loadMapObservations({ viewport: true });
                }
                const year = $id('timeline-year').value;
                $id('timeline-year').replaceChildren(new Option('选择年份', ''), ...this.timeline.years.map(y => new Option(`${y} 年`, y)));
                if (this.timeline.years.includes(Number(year))) $id('timeline-year').value = year;
                $id('timeline-toggle').disabled = !this.timeline.years.length;
                $id('timeline-year').disabled = !this.timeline.years.length;
                $id('timeline-toggle').title = this.timeline.years.length ? '逐年播放真实观测数据' : '当前保护等级没有可播放年份';
                $id('timeline-toggle').setAttribute('aria-label', this.timeline.years.length ? '年度播放' : '暂无可播放年份');
                this.updateTimelineButton();
            } catch (error) {
                $id('timeline-toggle').disabled = true;
                $id('timeline-toggle').innerHTML = '<i class="fas fa-play"></i>';
                $id('timeline-toggle').title = '年份加载失败';
                $id('timeline-toggle').setAttribute('aria-label', '年份加载失败');
                $id('thematic-note').textContent = error.message;
            }
        },

        updateTimelineButton: function() {
            const button = $id('timeline-toggle');
            if (!button) return;
            const available = this.timeline.years.length > 0;
            const playing = this.timeline.playing && available;
            button.innerHTML = `<i class="fas fa-${playing ? 'pause' : 'play'}"></i>`;
            button.title = playing ? '暂停年度播放' : (available ? '年度播放' : '当前保护等级没有可播放年份');
            button.setAttribute('aria-label', playing ? '暂停年度播放' : '年度播放');
        },

        pauseTimeline: function() {
            const state = this.timeline;
            state.playing = false; ++state.token;
            clearTimeout(state.timer); state.timer = null;
            this.updateTimelineButton();
        },

        selectMonitoringYear: function() {
            this.pauseTimeline();
            const year = Number($id('timeline-year').value);
            if (!this.timeline.years.includes(year)) return;
            $id('d-start').value = `${year}-01-01`; $id('d-end').value = `${year}-12-31`;
            this.loadMapObservations();
        },

        toggleTimeline: async function() {
            const state = this.timeline;
            if (state.playing) { this.pauseTimeline(); return; }
            if (!state.years.length) return;
            state.playing = true;
            this.updateTimelineButton();
            const token = ++state.token;
            const selected = Number($id('d-start').value.slice(0, 4));
            let index = Math.max(0, state.years.indexOf(selected));
            const advance = async () => {
                if (!state.playing || token !== state.token) return;
                const year = state.years[index];
                $id('timeline-year').value = String(year);
                $id('d-start').value = `${year}-01-01`; $id('d-end').value = `${year}-12-31`;
                // A frame waits for its data AND heat selection; no interval or
                // unbounded overlapping requests. Pan requests supersede it.
                await this.loadMapObservations({ playback: true });
                if (this._mapPending) await this._mapPending;
                if (!state.playing || token !== state.token) return;
                if (index >= state.years.length - 1) { this.pauseTimeline(); return; }
                index++;
                state.timer = setTimeout(advance, 1400);
            };
            await advance();
        },

        setProtectionFilter: function(filter) {
            this.pauseTimeline();
            this.protectionFilter = filter || 'all';
            document.querySelectorAll('[data-protection-filter]').forEach(btn => btn.classList.toggle('active', btn.dataset.protectionFilter === this.protectionFilter));
            this.loadMonitoringYears();
            this.loadMapObservations();
        },

        loadMapObservations: function(options = {}) {
            if (!options.playback && !options.viewport && !options.after) this.pauseTimeline();
            clearTimeout(this._recordRenderTimer);
            const key = filterKey();
            const firstPaint = key !== this._requestedFilterKey || !this._completeMapLoaded;
            if (key !== this._requestedFilterKey) {
                this._requestedFilterKey = key;
                this.invalidateBuffer(); this.closeDetailModal();
            }
            const seq = ++this._mapRequestSeq;
            this._mapController?.abort();
            const controller = this._mapController = new AbortController();
            const params = this.getMapObservationParams({ includeStats: key !== this._statsKey || !this.serverStats });
            // 首批和高缩放明细恢复为 1 万条；缓冲分析仍单独使用 5,000 条分页。
            params.zoom = this.map.getZoom(); params.page_size = 10000;
            if (options.after) params.after = options.after;
            $id('thematic-note').textContent = '正在加载当前视域…';
            $id('point-next').hidden = true;
            const request = (async () => {
                try {
                    if (firstPaint && !options.after) {
                        try {
                            const previewParams = { ...params, stage: 'preview', stats: '0' };
                            const previewResponse = await fetch(`/api/map-observations/?${new URLSearchParams(previewParams)}`, { signal: controller.signal });
                            if (seq !== this._mapRequestSeq || key !== filterKey()) return false;
                            if (previewResponse.ok) {
                                const preview = await previewResponse.json();
                                if (seq !== this._mapRequestSeq || key !== filterKey()) return false;
                                this.mapMode = 'points'; this.mapClusters = [];
                                this.pointPage = (preview.results || []).map(item => this.enrichObservation(item));
                                this.pageTruncated = false;
                                this.renderVisibleRecordMarkers();
                                $id('thematic-note').textContent = `已先显示 ${this.pointPage.length} 条记录，正在补全当前视域全部点位与统计…`;
                                // Let the browser paint before starting the complete query.
                                await new Promise(resolve => requestAnimationFrame(resolve));
                            }
                        } catch (error) {
                            if (error.name === 'AbortError') return false;
                            // A failed preview must not prevent the complete load.
                        }
                    }
                    if (seq !== this._mapRequestSeq || key !== filterKey()) return false;
                    const response = await fetch(`/api/map-observations/?${new URLSearchParams(params)}`, { signal: controller.signal });
                    const payload = await response.json();
                    if (!response.ok) throw new Error(payload.detail || '点位加载失败');
                    if (seq !== this._mapRequestSeq || key !== filterKey()) return false;
                    this._completeMapLoaded = true;
                    if (payload.stats) { this.serverStats = payload.stats; this._statsKey = key; }
                    this.mapMode = payload.mode; this.mapClusters = payload.clusters || [];
                    this.pointPage = (payload.results || []).map(item => this.enrichObservation(item));
                    this._recentRecords = (payload.recent || []).map(item => this.enrichObservation(item));
                    this.data = [...new Map([...this.pointPage, ...this._recentRecords].map(item => [item.id, item])).values()];
                    this.nextPointAfter = payload.next_after;
                    this.pageTruncated = payload.has_more || Boolean(options.after);
                    this.refresh();
                    const v = payload.viewport;
                    const mode = payload.mode === 'clusters' ? `聚合显示 ${this.mapClusters.length} 组，点击可放大` : `本页 ${this.pointPage.length} 条真实记录`;
                    $id('thematic-note').textContent = `当前视域 ${v.total_records} 条记录 / ${v.bird_count} 只 / ${v.species_count} 个物种。${mode}。${this.pageTruncated ? '明细分页显示；背景聚合保留全部分布，统计为完整结果。' : ''}`;
                    $id('point-next').hidden = !payload.has_more;
                    $id('point-pagination').hidden = payload.mode !== 'points' || !this.pageTruncated;
                    $id('point-page-note').textContent = `视域共 ${v.total_records} 条记录，本页 ${this.pointPage.length} 条；其他位置保留圆点，统计为完整结果。`;
                    if (this.heatmap.bounds) await this.buildHeatmapForBounds(this.heatmap.bounds);
                    this.layoutMonitoring();
                    return true;
                } catch (error) {
                    if (error.name === 'AbortError' || seq !== this._mapRequestSeq) return false;
                    $id('thematic-note').textContent = `${error.message}，请调整筛选或重试。`;
                    this.pauseTimeline(); return false;
                }
            })();
            this._mapPending = request;
            return request;
        },

        scheduleVisibleRecordMarkers: function() {
            clearTimeout(this._recordRenderTimer);
            // Invalidate immediately; an old viewport must not briefly replace
            // the new viewport during the debounce window.
            ++this._markerRenderSeq;
            ++this._mapRequestSeq; this._mapController?.abort();
            this._recordRenderTimer = setTimeout(() => this.loadMapObservations({ viewport: true }), 180);
        },

        renderVisibleRecordMarkers: function() {
            const seq = ++this._markerRenderSeq;
            this.layers.record.clearLayers(); this.recordMarkers = {};
            const raw = this.mapMode === 'points';
            // Background cells preserve distribution beyond the visible page.
            const groups = raw && !this.pageTruncated ? [] : this.mapClusters;
            const points = raw ? this.pointPage : [];
            let cursor = 0;
            const drawCluster = item => {
                const color = this.getProtectionColor(item.species_protection);
                const marker = L.circleMarker([item.lat, item.lng], {
                    renderer: this.clusterRenderer, radius: 6,
                    color: '#fff', weight: 1, fillColor: color, fillOpacity: raw ? 0.35 : 0.82,
                    bubblingMouseEvents: false, protectionGroup:item.species_protection, baseFillOpacity:raw ? 0.28 : 0.8
                }).bindTooltip(`${this.escapeHtml(item.species_protection)}：${item.cluster_size} 条记录，${item.count} 只；${item.cluster_size === 1 ? '点击查看详情' : '点击放大查看记录'}`);
                marker.on('click', () => {
                    if (this.heatmap.active || this.bufferAnalysis.picking) return;
                    if (item.cluster_size === 1) {
                        this.openDetailModal({id:item.record_id, lng:item.lng, lat:item.lat});
                        return;
                    }
                    const target = Math.min(18, this.map.getZoom() + 2);
                    this.map.setView([item.lat, item.lng], target);
                    if (this.map.getZoom() >= 18) this.loadMapObservations({ viewport: true });
                });
                marker.addTo(this.layers.record);
            };
            const drawPoint = item => {
                const marker = this.buildRecordMarker(item, this.currentStats || {});
                if (marker) { marker.addTo(this.layers.record); this.recordMarkers[item.id] = marker; }
            };
            const drawBatch = () => {
                if (seq !== this._markerRenderSeq) return;
                const end = Math.min(cursor + 900, groups.length + points.length);
                while (cursor < end) {
                    if (cursor < groups.length) drawCluster(groups[cursor]);
                    else drawPoint(points[cursor - groups.length]);
                    cursor++;
                }
                this.syncRecordMarkerVisibility();
                if (cursor < groups.length + points.length) requestAnimationFrame(drawBatch);
            };
            drawBatch();
        },

        renderRealTimeLogs: function() { original.renderRealTimeLogs.call(this, this._recentRecords); },

        showMonitoringHit: function(record) {
            const pos = this.getObservationPosition(record);
            if (!pos || !this.hitLayer) return;
            this.hitLayer.clearLayers();
            L.circleMarker([pos.lat, pos.lng], { pane:'monitorHitPane', interactive:false, radius:15, color:'#fff', weight:3, fillColor:'#00ADB5', fillOpacity:0.65 }).addTo(this.hitLayer);
        },

        openDetailModal: async function(record) {
            if (this.heatmap.active || this.bufferAnalysis.picking) return;
            this.pauseTimeline();
            this.showMonitoringHit(record);
            this._detailController?.abort();
            const controller = this._detailController = new AbortController();
            try {
                const params = this.getMapObservationParams();
                const response = await fetch(`/api/monitoring/records/${record.id}/?${new URLSearchParams(params)}`, { signal:controller.signal });
                const payload = await response.json();
                if (!response.ok) throw new Error(payload.detail || '详情加载失败');
                if (controller.signal.aborted) return;
                this._detailPayload = payload;
                original.openDetailModal.call(this, this.enrichObservation(payload.result), this.currentStats || {});
            } catch (error) {
                if (error.name !== 'AbortError') $id('thematic-note').textContent = error.message;
            }
        },

        closeDetailModal: function() {
            this._detailController?.abort(); this._detailPayload = null;
            this.hitLayer?.clearLayers(); original.closeDetailModal.call(this);
        },

        buildAutoHeatmap: function() {
            this.clearAutoHeatmap();
            if (!this.mapClusters.length) return;
            const points = this.mapClusters.map(item => ({ lat:item.lat, lng:item.lng, weight:Math.max(0, item.count) }));
            this.heatmap.autoLayer = this.createCanvasHeatLayer(points, this.map.getBounds().pad(0.16)).addTo(this.map);
        },

        buildHeatmapForBounds: async function(bounds) {
            const key = `${filterKey()}|${bounds.toBBoxString()}`;
            if (key === this._heatKey && this.heatmap.layer) return;
            const seq = this._heatSeq = (this._heatSeq || 0) + 1;
            this._heatController?.abort();
            const controller = this._heatController = new AbortController();
            this.clearAutoHeatmap(); this.heatmap.bounds = bounds;
            if (this.heatmap.layer) { this.map.removeLayer(this.heatmap.layer); this.heatmap.layer = null; }
            if (this.heatmap.boundsRect) this.map.removeLayer(this.heatmap.boundsRect);
            this.heatmap.boundsRect = L.rectangle(bounds, { color:'#2c3e50', weight:2, fill:false, dashArray:'8,5', interactive:false }).addTo(this.map);
            $('#heat-info').show(); $id('heat-info-text').textContent = '正在统计圈选范围…';
            this.layoutMonitoring();
            const params = this.getMapObservationParams();
            ['west','south','east','north'].forEach(k => delete params[k]);
            params.bbox = bounds.toBBoxString();
            try {
                const response = await fetch(`/api/monitoring/heatmap/?${new URLSearchParams(params)}`, { signal:controller.signal });
                const payload = await response.json();
                if (!response.ok) throw new Error(payload.detail || '热力统计失败');
                if (seq !== this._heatSeq || !this.heatmap.bounds) return;
                this._heatKey = key;
                const points = payload.points.map(item => ({ lat:item.lat, lng:item.lng, weight:Math.max(0, item.count) }));
                if (points.length) this.heatmap.layer = this.createCanvasHeatLayer(points, bounds).addTo(this.map);
                const s = payload.summary;
                $id('heat-info-text').textContent = `圈选完整统计：${s.total_records} 条记录，${s.bird_count} 只，${s.species_count} 个物种。热力按鸟类数量聚合。`;
            } catch (error) {
                if (error.name !== 'AbortError' && seq === this._heatSeq) $id('heat-info-text').textContent = error.message;
            }
        },

        clearHeatmap: function() {
            ++this._heatSeq; this._heatKey = null; this._heatController?.abort();
            original.clearHeatmap.call(this);
        },

        toggleHeatSelection: function(force) {
            const show = typeof force === 'boolean' ? force : !this.heatmap.active;
            if (show) { this.pauseTimeline(); this.toggleBufferAnalysis(false); this.toggleMonitoringTools(true); }
            original.toggleHeatSelection.call(this, show);
            this.layoutMonitoring();
        },

        invalidateBuffer: function() {
            const state = this.bufferAnalysis;
            ++state.seq; state.controller?.abort(); state.payload = null; state.params = null;
            state.layer.clearLayers(); $id('analysis-export').disabled = true;
            $id('analysis-run').disabled = false; $id('buffer-next').hidden = true;
            $id('analysis-results').replaceChildren();
            $id('analysis-scope').textContent = '沿用上方日期与保护等级；CSV 导出全部命中记录。';
            if (state.active) $id('analysis-status').textContent = '条件已变化，请重新运行分析。';
        },

        toggleBufferAnalysis: function(force) {
            const state = this.bufferAnalysis;
            const show = typeof force === 'boolean' ? force : !state.active;
            if (show) {
                this.pauseTimeline(); this.toggleHeatSelection(false); this.clearHeatmap(); this.closeDetailModal();
                this.toggleMonitoringTools(true);
            }
            state.active = show; state.picking = show && !state.center;
            $id('analysis-panel').classList.toggle('visible', show);
            $id('buffer-analysis-toggle').classList.toggle('active', show);
            document.body.classList.toggle('analysis-open', show);
            document.body.classList.toggle('analysis-selecting', state.picking);
            if (!show) { this.invalidateBuffer(); state.center = null; }
            else { this.drawBufferPreview(); $id('analysis-status').textContent = state.center ? '中心已选择，点击“运行分析”。' : '点击地图选择中心点，默认半径 500 米。'; }
            this.layoutMonitoring();
        },

        pickBufferCenter: function() {
            this.invalidateBuffer(); this.bufferAnalysis.picking = true;
            document.body.classList.add('analysis-selecting');
            $id('analysis-status').textContent = '点击地图重新选择中心点。';
        },

        drawBufferPreview: function() {
            const state = this.bufferAnalysis;
            state.layer.clearLayers();
            if (!state.center || !state.active) return;
            const radius = Number($id('buffer-radius').value);
            if (radius >= 50 && radius <= 10000) L.circle(state.center, { radius, color:'#1f6f78', weight:2, fillOpacity:0.08, interactive:false }).addTo(state.layer);
            L.circleMarker(state.center, { radius:6, color:'#fff', weight:2, fillColor:'#1f6f78', fillOpacity:1, interactive:false }).addTo(state.layer);
        },

        clearBufferAnalysis: function() {
            this.invalidateBuffer(); this.bufferAnalysis.center = null; this.bufferAnalysis.picking = true;
            document.body.classList.add('analysis-selecting');
            $id('analysis-status').textContent = '已清除。点击地图选择新的中心点。';
        },

        runBufferAnalysis: async function(after = null) {
            const state = this.bufferAnalysis;
            if (!state.center) { $id('analysis-status').textContent = '请先点击地图选择中心点。'; return; }
            const radius = Number($id('buffer-radius').value);
            if (!Number.isFinite(radius) || radius < 50 || radius > 10000) { $id('analysis-status').textContent = '半径请输入 50—10,000 米。'; return; }
            const seq = ++state.seq;
            state.controller?.abort();
            const controller = state.controller = new AbortController();
            const params = { lng:state.center.lng, lat:state.center.lat, radius,
                start:$id('d-start').value, end:$id('d-end').value, protection:this.protectionFilter, page_size:5000 };
            if (after) params.after = after;
            state.payload = null; state.params = null;
            $id('analysis-export').disabled = true; $id('analysis-run').disabled = true;
            $id('buffer-next').hidden = true; $id('analysis-results').replaceChildren();
            $id('analysis-status').textContent = '正在计算缓冲范围与完整统计…';
            try {
                const response = await fetch(`/api/monitoring/buffer/?${new URLSearchParams(params)}`, { signal:controller.signal });
                const payload = await response.json();
                if (!response.ok) throw new Error(payload.detail || '缓冲分析失败');
                if (seq !== state.seq || !state.active) return;
                state.payload = payload; state.params = params; state.picking = false;
                document.body.classList.remove('analysis-selecting');
                state.layer.clearLayers();
                L.geoJSON(payload.buffer, { style:{ color:'#1f6f78', weight:2, fillOpacity:0.1 }, interactive:false }).addTo(state.layer);
                L.geoJSON(payload.routes, { style:{ color:'#F39C12', weight:5 }, onEachFeature:(f,l) => l.bindTooltip(this.escapeHtml(f.properties.name)) }).addTo(state.layer);
                payload.results.forEach(item => {
                    const marker = L.circleMarker([item.lat,item.lng], { radius:5, color:this.getProtectionColor(this.getProtectionGroup(item.species_protection)), fillOpacity:0.9, bubblingMouseEvents:false });
                    marker.on('click', () => this.openDetailModal(item)); marker.addTo(state.layer);
                });
                const s = payload.summary;
                $id('analysis-status').textContent = `半径 ${radius} 米：${s.total_records} 条记录，${s.bird_count} 只，${s.species_count} 个物种；命中 ${s.matched_routes} 条样线。当前明细 ${payload.results.length} 条${payload.truncated ? '（已截断，可查看下一页）' : ''}。${payload.routes_truncated ? '样线图形仅显示前 100 条。' : ''}`;
                $id('analysis-scope').textContent = `时间：${params.start || '不限'} 至 ${params.end || '不限'}；保护等级：${params.protection === 'all' ? '全部' : params.protection}。统计与 CSV 均覆盖全部符合条件的已审核记录；CSV 导出观测记录，不含样线几何。`;
                const list = $id('analysis-results');
                payload.results.slice(0,50).forEach(item => {
                    const li = document.createElement('li'), button = document.createElement('button');
                    button.textContent = `${item.species_name} · ${item.count} 只 · ${item.observation_time}`;
                    button.onclick = () => this.openDetailModal(item); li.append(button); list.append(li);
                });
                if (payload.results.length > 50) { const li = document.createElement('li'); li.textContent='列表显示本页前 50 条，地图显示本页全部明细。'; list.append(li); }
                $id('analysis-export').disabled = false;
                $id('buffer-next').hidden = !payload.has_more;
            } catch (error) {
                if (error.name !== 'AbortError' && seq === state.seq) { state.layer.clearLayers(); $id('analysis-status').textContent = error.message; }
            } finally {
                if (seq === state.seq) { $id('analysis-run').disabled = false; this.layoutMonitoring(); }
            }
        },

        exportBufferResults: function() {
            const state = this.bufferAnalysis;
            if (!state.payload || !state.params) return;
            const params = { ...state.params }; delete params.after; delete params.page_size;
            const link = document.createElement('a');
            link.href = `/api/monitoring/buffer.csv?${new URLSearchParams(params)}`;
            link.download = '缓冲分析-全部命中记录.csv'; link.click();
        }
    });
}
