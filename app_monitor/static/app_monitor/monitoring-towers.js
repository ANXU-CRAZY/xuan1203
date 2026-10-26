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
    const symbol = () => '<svg class="monitoring-tower-symbol" viewBox="0 0 36 44" aria-hidden="true">' +
        '<path d="M13 21 7 40M23 21l6 19M6 40h24M11 29h14M9 36h18M12 29l13 7M24 29l-13 7" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/>' +
        '<path d="M7 12 18 5l11 7H7Z" fill="currentColor" stroke="#fff" stroke-width="1.3"/>' +
        '<path d="M10 13h16v10H10Z" fill="currentColor" stroke="#fff" stroke-width="1.3"/>' +
        '<path d="M13 16h4v4h-4Zm6 0h4v4h-4Z" fill="#fff"/>' +
        '<path d="M18 5V2" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>';
    const iconSize=zoom=>{
        const width=zoom<13 ? 18 : zoom<15 ? 22 : 26;
        return [width,Math.round(width*44/36)];
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
    Object.assign(app,{
        monitoringTowerMarkers:[],
        init: function() {
            originalInit.call(this);
            this.monitoringTowerInitialZoom=this.map.getZoom();
            this.map.createPane('monitoringTowerPane');
            this.map.getPane('monitoringTowerPane').style.zIndex='630';
            for (const [kind,type] of Object.entries(TYPES)) {
                this.layerControl.addOverlay(this.layers[type.key],layerLabel(kind));
                this.layers[type.key].addTo(this.map);
            }
            this.map.on('zoomend moveend overlayadd overlayremove',()=>this.updateMonitoringTowerLabels());
            this.map.on('click',()=>this.clearMonitoringTowerSelection());
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
            selected.marker.getElement()?.classList.remove('is-selected');
            // Remove only this tower's halo, preserving any newer bird highlight.
            if (selected.halo) this.hitLayer?.removeLayer(selected.halo);
            selected.popup?.remove();
        },
        openDetailModal: function(...args) {
            if (!this.heatmap.active && !this.bufferAnalysis?.picking) {
                this.clearMonitoringTowerSelection();
                this.map.closePopup();
            }
            return originalOpenDetail.apply(this,args);
        },
        closeDetailModal: function(...args) {
            this.clearMonitoringTowerSelection();
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
                        this.closeDetailModal();
                        this.pauseTimeline?.();
                        this.showMonitoringHit({lng,lat});
                        const top=document.getElementById('filter-bar').getBoundingClientRect().bottom+12;
                        const popup=L.popup({
                            className:'monitoring-tower-popup',maxWidth:300,minWidth:210,
                            autoPanPaddingTopLeft:L.point(18,top),autoPanPaddingBottomRight:L.point(18,100),
                            offset:L.point(0,0)
                        },marker).setLatLng(marker.getLatLng()).setContent(this.monitoringTowerPopup(feature));
                        this._selectedMonitoringTower={marker,halo:this.hitLayer?.getLayers()[0],popup};
                        marker.getElement()?.classList.add('is-selected');
                        popup.on('remove',()=>{
                            if (this._selectedMonitoringTower?.marker===marker) this.clearMonitoringTowerSelection();
                        });
                        popup.openOn(this.map);
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
            const zoom=this.map.getZoom(),visible=zoom>this.monitoringTowerInitialZoom+1e-6;
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
