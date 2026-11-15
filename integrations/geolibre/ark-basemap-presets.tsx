/** Additional Fangzhou choices inside GeoLibre's original background picker. */
import { DEFAULT_ELLIPSOID_ID, useAppStore } from "@geolibre/core";
import { useEffect, useState } from "react";

const presets = [
  ["vector", "天地图电子图"],
  ["imagery", "天地图影像图"],
  ["amap", "高德地图"],
] as const;

export function arkBasemapChoice(styleUrl: string) {
  try {
    const url = new URL(styleUrl, location.href);
    if (url.origin === location.origin && url.pathname.endsWith('/workbench/geolibre/basemap.json')) {
      const kind = url.searchParams.get('kind') || 'vector';
      if (['vector', 'imagery', 'amap', 'blank'].includes(kind)) return kind;
    }
  } catch { /* Other native styles remain ordinary native choices. */ }
  return null;
}

export function ArkBasemapPresets({ onSelect }: { onSelect: () => void }) {
  const url = useAppStore((s) => s.basemapStyleUrl);
  const kind = arkBasemapChoice(url);
  const storedLabels = new URL(url, location.href).searchParams.get('labels') !== '0';
  const [labels, setLabels] = useState(storedLabels);
  useEffect(() => setLabels(storedLabels), [storedLabels]);
  const independentLabels = kind === 'vector' || kind === 'imagery';

  function change(nextKind: string, nextLabels: boolean, close: boolean) {
    const state = useAppStore.getState();
    state.setBasemapVisible(true);
    if (state.preferences.map.ellipsoidId !== DEFAULT_ELLIPSOID_ID) {
      state.setPreferences({ ...state.preferences, map: { ...state.preferences.map, ellipsoidId: DEFAULT_ELLIPSOID_ID } });
    }
    window.parent.postMessage(
      { source: 'ark-workbench-map', type: 'basemap-change', kind: nextKind, labels: nextLabels },
      location.origin,
    );
    if (close) onSelect();
  }

  return <section className="ark-basemap-presets" aria-label="常用底图">
    <h3>常用底图</h3>
    <div className="ark-basemap-preset-grid">
      {presets.map(([value, label]) => <button type="button" key={value} aria-pressed={kind === value}
        onClick={() => change(value, labels, true)}>{label}</button>)}
    </div>
    <label className="ark-preset-labels"><input type="checkbox" checked={labels} disabled={!independentLabels}
      aria-label="天地图注记" onChange={(event) => { setLabels(event.target.checked); change(kind!, event.target.checked, false); }} />
      <span>天地图注记</span><small>{kind === 'amap' ? '高德底图自带注记' : '适用于天地图电子图与影像图'}</small>
    </label>
  </section>;
}
