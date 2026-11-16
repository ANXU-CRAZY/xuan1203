/* Infrastructure overlays remain independent of observation filters/statistics. */
function installMonitoringTowers(app) {
    const originalInit = app.init;
    const originalOpenDetail = app.openDetailModal;
    const originalCloseDetail = app.closeDetailModal;
    const originalFitDefaultRegionView = app.fitDefaultRegionView;
    const TYPES = {
        existing: { key:'monitoringTowers', name:'监控塔点位' },
        planned: { key:'plannedMonitoringTowers', name:'拟新建监控塔点位' }
    };
    const TOWER_LABEL_ZOOM=14;
    const COVERAGE_RADIUS=2500;
    const RadarSweep=L.Layer.extend({
        initialize(center,bounds,planned=false) { this.center=center; this.bounds=bounds; this.planned=planned; },
        onAdd(map) {
            this.map=map;
            this.element=L.DomUtil.create('div','tower-radar-footprint'+(this.planned?' is-planned':''),map.getPane('towerScanPane'));
            this.element.innerHTML='<div class="tower-radar-sweep"></div><div class="tower-radar-crosshair"></div>';
            this.update();
        },
        getEvents() { return {zoom:this.update,move:this.update,viewreset:this.update,resize:this.update}; },
        update() {
            const nw=this.map.latLngToLayerPoint(this.bounds.getNorthWest());
            const se=this.map.latLngToLayerPoint(this.bounds.getSouthEast());
            L.DomUtil.setPosition(this.element,nw);
            this.element.style.width=(se.x-nw.x)+'px';
            this.element.style.height=(se.y-nw.y)+'px';
        },
        onRemove() { this.element.remove(); this.map=null; }
    });
    const symbol = () => '<span class="monitoring-tower-symbol" aria-hidden="true"><span class="tower-logo-disc"><img src="/static/app_monitor/img/monitoring-tower-logo.png" alt="" draggable="false"></span></span>';
    const iconSize=zoom=>{
        const width=zoom<13 ? 24 : zoom<15 ? 30 : 36;
        return [width,Math.round(width*1.18)];
    };
    const towerIcon=(kind,zoom)=>{
        const [width,height]=iconSize(zoom);
        return L.divIcon({
            className:'monitoring-tower-marker '+(kind==='planned'?'is-planned':''),
            html:symbol(),iconSize:[width,height],iconAnchor:[width/2,height-2],
            tooltipAnchor:[width/2,-height/2],popupAnchor:[0,-height+2]
        });
    };
    const layers = Object.fromEntries(Object.values(TYPES).map(type => [type.key,L.layerGroup()]));
    const layerLabel=(kind,error=false)=>'<span class="tower-layer-label '+(kind==='planned'?'is-planned':'')+
        '" data-tower-layer="'+kind+'">'+symbol()+'<span>'+TYPES[kind].name+'</span>'+
        (error?'<span class="tower-layer-error" aria-live="polite">加载失败</span>':'')+'</span>';
    Object.assign(app.layers,layers);
    app.layers.monitoringCoverage=L.layerGroup();
    app.layers.monitoringUncovered=L.layerGroup();
    Object.assign(app,{
        monitoringTowerMarkers:[],
        init: function() {
            originalInit.call(this);
            this.monitoringTowerInitialZoom=this.map.getZoom();
            this.map.createPane('monitoringTowerPane');
            this.map.getPane('monitoringTowerPane').style.zIndex='630';
            for (const [name,index] of [['towerCoveragePane',405],['towerScanPane',615]]) {
                this.map.createPane(name).style.zIndex=String(index);
                this.map.getPane(name).style.pointerEvents='none';
            }
            this.towerCoverageGroups={existing:L.layerGroup(),planned:L.layerGroup()};
            this.towerScanLayer=L.layerGroup().addTo(this.map);
            this.layerControl.addOverlay(this.layers.monitoringCoverage,
                '<span data-tower-layer="coverage">监测覆盖范围</span>');
            this.layerControl.addOverlay(this.layers.monitoringUncovered,
                '<span data-tower-layer="uncovered" title="保护区内，按现有监测塔估算">未覆盖区域</span>');
            this.layers.monitoringCoverage.addTo(this.map);
            this.map.on('overlayadd',event=>{
                if (event.layer===this.layers.monitoringUncovered) this.loadUncoveredMonitoringArea();
            });
            this.map.on('overlayremove',event=>{
                if (event.layer===this.layers.monitoringCoverage) this.clearMonitoringTowerSelection();
            });
            for (const [kind,type] of Object.entries(TYPES)) {
                this.layerControl.addOverlay(this.layers[type.key],layerLabel(kind));
                if (kind==='existing') this.layers[type.key].addTo(this.map);
            }
            this.map.on('zoomend moveend overlayadd overlayremove',()=>this.updateMonitoringTowerLabels());
            this.map.on('click',()=>this.clearMonitoringTowerSelection());
            document.addEventListener('keydown',event=>{
                if (event.key==='Escape') this.clearMonitoringTowerSelection();
            });
            this.loadMonitoringTowers();
        },
        fitDefaultRegionView: function(...args) {
            const result=originalFitDefaultRegionView.apply(this,args);
            if (!this._hasInitialView) {
                // Use the final fitted initial view, which varies by viewport.
                this.monitoringTowerInitialZoom=this.map.getZoom();
                this.updateMonitoringTowerLabels();
            }
            return result;
        },
        clearMonitoringTowerSelection: function() {
            const selected=this._selectedMonitoringTower;
            if (!selected) return;
            this._selectedMonitoringTower=null;
            if (selected.startScan) this.map.off('moveend',selected.startScan);
            clearTimeout(selected.scanTimer);
            this.towerScanLayer.clearLayers();
            selected.marker.getElement()?.classList.remove('is-selected');
            // Remove only this tower's halo, preserving any newer bird highlight.
            if (selected.halo) this.hitLayer?.removeLayer(selected.halo);
            selected.popup?.remove();
        },
        loadUncoveredMonitoringArea: async function() {
            if (this._towerUncoveredLoaded || this._towerUncoveredLoading) return;
            this._towerUncoveredLoading=true;
            try {
                const response=await fetch('/api/monitoring/tower-coverage/');
                if (!response.ok) throw new Error('HTTP '+response.status);
                const data=await response.json();
                this.layers.monitoringUncovered.clearLayers();
                L.geoJSON(data,{pane:'towerCoveragePane',interactive:false,
                    style:{color:'#b78854',weight:1,dashArray:'3 5',fillColor:'#ddc5a5',fillOpacity:0.25}
                }).addTo(this.layers.monitoringUncovered);
                this.monitoringCoverageSummary=data.metadata;
                this._towerUncoveredLoaded=true;
                if (this.monitoringCoverageError) {
                    this.layerControl.removeLayer(this.layers.monitoringUncovered);
                    this.layerControl.addOverlay(this.layers.monitoringUncovered,
                        '<span data-tower-layer="uncovered" title="保护区内，按现有监测塔估算">未覆盖区域</span>');
                }
                this.monitoringCoverageError=null;
            } catch(error) {
                this.monitoringCoverageError=error.message;
                this.layerControl.removeLayer(this.layers.monitoringUncovered);
                this.layerControl.addOverlay(this.layers.monitoringUncovered,
                    '<span data-tower-layer="uncovered">未覆盖区域 <span class="tower-layer-error">加载失败，请重新勾选</span></span>');
                console.warn('监测未覆盖区域加载失败',error);
            } finally { this._towerUncoveredLoading=false; }
        },
        focusMonitoringTower: function(marker) {
            this.clearMonitoringTowerSelection();
            this.map.stop();
            this.closeDetailModal();
            this.pauseTimeline?.();
            if (innerWidth<=768) {
                this.toggleDashboardPanel(false);
                if (this.bufferAnalysis?.active) this.toggleBufferAnalysis(false);
            }
            if (!this.map.hasLayer(this.layers.monitoringCoverage)) this.layers.monitoringCoverage.addTo(this.map);
            const selected=this._selectedMonitoringTower={marker};
            marker.getElement()?.classList.add('is-selected');
            const center=marker.getLatLng();
            const planned=marker.feature.properties.kind==='planned';
            const color=planned?'#c78a37':'#168f8c';
            const outer=L.circle(center,{radius:COVERAGE_RADIUS,pane:'towerScanPane',interactive:false,
                stroke:false,fillColor:color,fillOpacity:0.04});
            // Add temporarily so Leaflet computes geographic circle bounds.
            outer.addTo(this.towerScanLayer);
            const bounds=outer.getBounds();
            this.towerScanLayer.clearLayers();
            let started=false;
            selected.startScan=()=>{
                if (started || this._selectedMonitoringTower!==selected || !this.map.hasLayer(this.layers.monitoringCoverage)) return;
                started=true;
                clearTimeout(selected.scanTimer);
                this.map.off('moveend',selected.startScan);
                outer.addTo(this.towerScanLayer);
                new RadarSweep(center,bounds,planned).addTo(this.towerScanLayer);
            };
            const mapRect=this.map.getContainer().getBoundingClientRect(),margin=32;
            let top=margin,bottom=margin,right=margin,left=margin;
            for (const selector of ['.top-beam','#filter-bar']) {
                const r=document.querySelector(selector)?.getBoundingClientRect();
                if (r?.height) top=Math.max(top,r.bottom-mapRect.top+margin);
            }
            const bottomBar=document.querySelector('.bottom-actions')?.getBoundingClientRect();
            if (bottomBar?.height) bottom=Math.max(bottom,mapRect.bottom-bottomBar.top+margin);
            const widgets=document.querySelector('.dashboard-module-controls')?.getBoundingClientRect();
            if (widgets?.width && widgets.left>mapRect.left+mapRect.width*0.35)
                right=Math.max(right,mapRect.right-widgets.left+16);
            for (const el of document.querySelectorAll('#detail-panel:not(.dashboard-closed),#analysis-panel.visible')) {
                const r=el.getBoundingClientRect();
                if (!r.width || !r.height || getComputedStyle(el).display==='none') continue;
                if (innerWidth>768 && r.left>mapRect.left+mapRect.width*0.35)
                    right=Math.max(right,mapRect.right-r.left+margin);
                else if (r.top>mapRect.top+mapRect.height/2) bottom=Math.max(bottom,mapRect.bottom-r.top+margin);
            }
            // Keep usable space on narrow/short screens while respecting fixed controls.
            right=Math.min(right,mapRect.width*0.65);
            top=Math.min(top,mapRect.height*0.4);
            bottom=Math.min(bottom,mapRect.height-top-100);
            this.map.once('moveend',selected.startScan);
            this.map.flyToBounds(bounds,{paddingTopLeft:[left,top],paddingBottomRight:[right,bottom],
                maxZoom:16,duration:1.25,animate:!matchMedia('(prefers-reduced-motion: reduce)').matches});
            selected.scanTimer=setTimeout(selected.startScan,1450);
        },
        openDetailModal: function(...args) {
            if (!this.heatmap.active && !this.bufferAnalysis?.picking) {
                this.clearMonitoringTowerSelection();
                this.map.closePopup();
            }
            return originalOpenDetail.apply(this,args);
        },
        closeDetailModal: function(...args) {
            // Observation refreshes also close their detail modal; infrastructure
            // selection should survive those unrelated requests.
            this.map.closePopup();
            return originalCloseDetail.apply(this,args);
        },
        monitoringTowerPopup: function(feature) {
            const props=feature.properties, type=TYPES[props.kind];
            return '<div class="region-popup tower-popup '+(props.kind==='planned'?'is-planned':'')+'">' +
                '<div class="tower-popup-heading">'+symbol()+'<div><strong>'+this.escapeHtml(props.name)+'</strong>' +
                '<span class="tower-popup-badge">'+type.name+'</span></div></div></div>';
        },
        loadMonitoringTowers: async function() {
            try {
                const response=await fetch('/static/app_monitor/geo/monitoring_towers.geojson?v=20261026-1');
                if (!response.ok) throw new Error('HTTP '+response.status);
                const data=await response.json();
                if (data.type!=='FeatureCollection' || !Array.isArray(data.features)) throw new Error('监控塔数据格式无效');
                const ids=new Set();
                for (const feature of data.features) {
                    const p=feature.properties,c=feature.geometry?.coordinates;
                    if (feature.geometry?.type!=='Point' || !TYPES[p?.kind] || typeof p.name!=='string' || !p.name.trim() ||
                        typeof p.source!=='string' || c?.length!==2 || !c.every(Number.isFinite) ||
                        Math.abs(c[0])>180 || Math.abs(c[1])>90 || !feature.id || ids.has(feature.id)) throw new Error('监控塔点位内容无效');
                    ids.add(feature.id);
                }
                // Validate all records before replacing either overlay.
                this.clearMonitoringTowerSelection();
                Object.values(layers).forEach(layer=>layer.clearLayers());
                this.monitoringTowerMarkers=[];
                Object.values(this.towerCoverageGroups).forEach(group=>group.clearLayers());
                for (const feature of data.features) {
                    const p=feature.properties,[lng,lat]=feature.geometry.coordinates;
                    const marker=L.marker([lat,lng],{
                        pane:'monitoringTowerPane',bubblingMouseEvents:false,
                        title:p.name,alt:p.name,keyboard:true,riseOnHover:true,
                        icon:towerIcon(p.kind,this.map.getZoom())
                    });
                    marker.feature=feature;
                    marker.bindTooltip(this.escapeHtml(p.name),{
                        direction:'right',className:'monitoring-tower-tooltip '+(p.kind==='planned'?'is-planned':'')
                    });
                    // Explicit popups prevent bindPopup's automatic click
                    // handler from bypassing heat/buffer selection priority.
                    marker.on('click',event=>{
                        if (this.heatmap.active) return;
                        if (this.bufferAnalysis?.picking) {
                            this.map.fire('click',{latlng:marker.getLatLng(),originalEvent:event.originalEvent});
                            return;
                        }
                        this.focusMonitoringTower(marker);
                    });
                    marker.on('keypress',event=>{
                        const key=event.originalEvent?.key;
                        if (key==='Enter' || key===' ') {
                            L.DomEvent.preventDefault(event.originalEvent);
                            marker.fire('click',{originalEvent:event.originalEvent});
                        }
                    });
                    marker.on('remove',()=>{
                        if (this._selectedMonitoringTower?.marker===marker) this.clearMonitoringTowerSelection();
                    });
                    marker.addTo(this.layers[TYPES[p.kind].key]);
                    this.monitoringTowerMarkers.push(marker);
                    L.circle([lat,lng],{radius:COVERAGE_RADIUS,pane:'towerCoveragePane',interactive:false,
                        stroke:false,fillColor:p.kind==='planned'?'#c78a37':'#168f8c',
                        fillOpacity:p.kind==='planned'?0.07:0.12
                    }).addTo(this.towerCoverageGroups[p.kind]);
                }
                this.updateMonitoringTowerLabels();
                for (const [kind,type] of Object.entries(TYPES)) {
                    // Update the registered label too: Leaflet rebuilds the
                    // control when layers are added/removed programmatically.
                    this.layerControl.removeLayer(this.layers[type.key]);
                    this.layerControl.addOverlay(this.layers[type.key],layerLabel(kind));
                }
                this.monitoringTowersError=null;
                this.monitoringTowersLoaded=true;
            } catch(error) {
                this.monitoringTowersError=error.message;
                for (const [kind,type] of Object.entries(TYPES)) {
                    this.layerControl.removeLayer(this.layers[type.key]);
                    this.layerControl.addOverlay(this.layers[type.key],layerLabel(kind,true));
                }
                console.warn('监控塔点位加载失败：',error);
            }
        },
        updateMonitoringTowerLabels: function() {
            const coverage=this.layers.monitoringCoverage;
            for (const [kind,type] of Object.entries(TYPES)) {
                const group=this.towerCoverageGroups[kind],show=this.map.hasLayer(this.layers[type.key]);
                if (show && !coverage.hasLayer(group)) coverage.addLayer(group);
                if (!show && coverage.hasLayer(group)) coverage.removeLayer(group);
            }
            const zoom=this.map.getZoom(),visible=this.map.hasLayer(coverage) || zoom>this.monitoringTowerInitialZoom+1e-6;
            this.map.getPane('monitoringTowerPane').classList.toggle('monitoring-towers-hidden',!visible);
            if (!visible) this.clearMonitoringTowerSelection();
            const [width,height]=iconSize(zoom);
            const mapRect=this.map.getContainer().getBoundingClientRect();
            const hits=(a,b)=>a.left<b.right && a.right>b.left && a.top<b.bottom && a.bottom>b.top;
            const obstacles=[...document.querySelectorAll('.top-beam,#filter-bar,#rank-panel,#detail-panel,.leaflet-control-layers')]
                .map(el=>el.getBoundingClientRect()).filter(rect=>rect.width && rect.height);
            const positions=new Map(),icons=[];
            for (const marker of this.monitoringTowerMarkers) {
                if (marker.options.icon.options.iconSize[0]!==width) {
                    marker.setIcon(towerIcon(marker.feature.properties.kind,zoom));
                    if (this._selectedMonitoringTower?.marker===marker) marker.getElement()?.classList.add('is-selected');
                }
                if (visible && this.map.hasLayer(marker)) {
                    const p=this.map.latLngToContainerPoint(marker.getLatLng());
                    const x=p.x+mapRect.left,y=p.y+mapRect.top;
                    positions.set(marker,{x,y});
                    icons.push({left:x-width/2-3,right:x+width/2+3,top:y-height-2,bottom:y+4});
                }
            }
            const context=(this._towerLabelCanvas ||= document.createElement('canvas')).getContext('2d');
            context.font='600 12px '+getComputedStyle(this.map.getContainer()).fontFamily;
            const occupied=[];
            // Preserve every point; only omit colliding persistent labels.
            // Suppressed names remain available on hover, keyboard focus and click.
            for (const marker of this.monitoringTowerMarkers) {
                const position=positions.get(marker);
                let permanent=false,direction='right';
                if (position) {
                    const labelWidth=Math.min(Math.ceil(context.measureText(marker.feature.properties.name).width)+18,260,innerWidth-48);
                    const candidates=['right','left'].map(side=>{
                        const left=side==='right' ? position.x+width/2+8 : position.x-width/2-8-labelWidth;
                        return {direction:side,left,right:left+labelWidth,top:position.y-height/2-13,bottom:position.y-height/2+13};
                    }).filter(box=>box.left>=mapRect.left+8 && box.right<=mapRect.right-8 &&
                                    box.top>=mapRect.top+8 && box.bottom<=mapRect.bottom-8);
                    direction=candidates[0]?.direction || 'right';
                    const chosen=zoom>=TOWER_LABEL_ZOOM && candidates.find(box=>
                        ![...obstacles,...icons,...occupied].some(other=>hits(box,other)));
                    if (chosen) {
                        direction=chosen.direction;
                        permanent=true;
                        occupied.push({...chosen,left:chosen.left-5,right:chosen.right+5,top:chosen.top-4,bottom:chosen.bottom+4});
                    }
                }
                const tip=marker.getTooltip();
                const offset=direction==='left' ? -width : 0;
                if (tip && (tip.options.permanent!==permanent || tip.options.direction!==direction ||
                    L.point(tip.options.offset).x!==offset)) {
                    const text=tip.getContent(),options={...tip.options,permanent,direction,offset:L.point(offset,0)};
                    marker.unbindTooltip().bindTooltip(text,options);
                }
                if (!visible) marker.closeTooltip();
            }
            this.layoutMonitoring?.();
        }
    });
}
