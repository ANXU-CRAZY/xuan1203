/* Use the bird workbench's WGS84 Tianditu map without touching SAM inference. */
(function () {
  'use strict';
  window.installLandMap = function () {
    const el = id => document.getElementById(id);
    const box = el('landGeoMap');
    if (!box || box.dataset.ready) return;
    box.dataset.ready = 'true';
    const tip = (message, error = false) => {
      el('landMapTip').textContent = message;
      el('landMapTip').dataset.error = String(error);
    };
    // Stop native canvas/location fallbacks: automatic viewer location must not
    // become the image's capture coordinate. EXIF import remains native.
    window.bindGpsMap = function () {};
    window.autoFillCoordsFromPosition = function () {};
    const valid = (lat, lon) => Number.isFinite(lat) && Number.isFinite(lon) && Math.abs(lat) <= 90 && Math.abs(lon) <= 180;
    let map = null, marker = null, lastCoordinate = '';
    const showPoint = (lat, lon) => {
      if (!map || !valid(lat, lon)) return;
      if (marker) marker.setLatLng([lat, lon]);
      else marker = L.marker([lat, lon]).addTo(map);
      marker.bindPopup(`纬度 ${lat.toFixed(6)}<br>经度 ${lon.toFixed(6)}`);
      const key = `${lat},${lon}`;
      if (key !== lastCoordinate) map.panTo([lat, lon]);
      lastCoordinate = key;
    };
    window.drawGpsMap = function () {
      const lat = parseFloat(el('inLat').value), lon = parseFloat(el('inLon').value);
      if (valid(lat, lon)) showPoint(lat, lon);
      else {
        const c = currentCoord();
        if (c && valid(Number(c.lat), Number(c.lon))) showPoint(Number(c.lat), Number(c.lon));
        else if (marker && map) { marker.remove(); marker = null; lastCoordinate = ''; }
      }
    };
    const choose = (lat, lon, zoom) => {
      if (!valid(lat, lon)) { tip('坐标超出范围：纬度 ±90，经度 ±180', true); return; }
      applyPickedCoord(lat, lon);
      fillMissingObjectCoords();
      if (zoom) map.setView([lat, lon], zoom);
      marker?.openPopup();
      tip(`已选坐标：${lat.toFixed(6)}, ${lon.toFixed(6)}`);
    };
    const locate = (select) => {
      if (!navigator.geolocation) { if (select) tip('浏览器不支持定位，请检索地点或点地图取坐标', true); return; }
      if (select) tip('正在获取当前位置…');
      navigator.geolocation.getCurrentPosition(position => {
        const {latitude: lat, longitude: lon} = position.coords;
        if (!select && lastCoordinate) return;
        if (select) choose(lat, lon, 14);
        else { map.setView([lat, lon], 11); tip('已定位到当前位置；点地图取坐标'); }
      }, () => { if (select) tip('定位失败，请允许浏览器定位，或检索地点、点地图取坐标', true); },
      {enableHighAccuracy: true, timeout: 8000, maximumAge: 60000});
    };
    window.autoLocateCurrent = function () { if (map) locate(false); };
    window.useCurrentCoords = function () {
      if (!map) return;
      const point = marker ? marker.getLatLng() : map.getCenter();
      choose(point.lat, point.lng);
    };
    if (!window.L || !window.LAND_MAP_CONFIG?.tdtKey) {
      tip('天地图未配置或地图组件未加载，请检查地图授权与网络', true);
      return;
    }
    map = L.map(box, {zoomControl: false, attributionControl: true}).setView([34, 108], 4);
    const key = encodeURIComponent(window.LAND_MAP_CONFIG.tdtKey);
    const url = layer => `https://t{s}.tianditu.gov.cn/${layer}_w/wmts?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0&LAYER=${layer}&STYLE=default&TILEMATRIXSET=w&FORMAT=tiles&TILEMATRIX={z}&TILEROW={y}&TILECOL={x}&tk=${key}`;
    for (const layer of ['vec', 'cva']) {
      L.tileLayer(url(layer), {subdomains: '01234567', maxZoom: 18, minZoom: 2,
        ...(layer === 'cva' ? {pane: 'overlayPane'} : {attribution: '&copy; 天地图 · 国家地理信息公共服务平台'})})
        .on('tileerror', () => tip('天地图加载失败，请检查网络或地图授权', true)).addTo(map);
    }
    map.on('click', e => choose(e.latlng.lat, e.latlng.lng));
    el('landGeoLocateButton').addEventListener('click', () => locate(true));
    ['inLat', 'inLon'].forEach(id => el(id).addEventListener('change', window.drawGpsMap));
    const searchButton = el('landGeoSearchButton');
    const search = async () => {
      const query = el('landGeoSearch').value.trim();
      if (!query || searchButton.disabled) return;
      const pair = query.match(/^(-?\d+(?:\.\d+)?)\s*[,，\s]\s*(-?\d+(?:\.\d+)?)$/);
      if (pair) {
        let lat = Number(pair[1]), lon = Number(pair[2]);
        if (Math.abs(lat) > 90 && Math.abs(lon) <= 90) [lat, lon] = [lon, lat];
        choose(lat, lon, 14);
        return;
      }
      searchButton.disabled = true;
      tip('正在检索地点…');
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 10000);
      try {
        const params = new URLSearchParams({postStr: JSON.stringify({keyWord: query, level: 12,
          mapBound: '73,18,135,54', queryType: 1, start: 0, count: 5}), type: 'query', tk: window.LAND_MAP_CONFIG.tdtKey});
        const response = await fetch(`https://api.tianditu.gov.cn/v2/search?${params}`, {signal: controller.signal});
        if (!response.ok) throw new Error('检索请求失败');
        const data = await response.json();
        const point = data.pois?.[0]?.lonlat || data.area?.lonlat;
        if (!point) { tip('未找到该地点，请换个名称或直接输入经纬度', true); return; }
        const [lon, lat] = point.split(',').map(Number);
        choose(lat, lon, 14);
      } catch (_) { tip('地点检索失败，请检查网络后重试，或直接输入经纬度', true); }
      finally { clearTimeout(timeout); searchButton.disabled = false; }
    };
    searchButton.addEventListener('click', search);
    el('landGeoSearch').addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); search(); } });
    new ResizeObserver(() => map.invalidateSize({pan: false})).observe(box);
    window.drawGpsMap();
  };
})();
