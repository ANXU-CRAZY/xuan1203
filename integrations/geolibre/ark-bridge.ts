/* Same-origin bridge between the workbench and the GeoLibre editor. */
import {excludeHiddenFieldsFromProject, parseProject, redactProjectCredentials,
    serializeProject, useAppStore, type GeoLibreProject} from '@geolibre/core';
import type {MapEngine} from '@geolibre/map';
let mapController: () => MapEngine | null = () => null;
export function setArkMapController(getter: () => MapEngine | null) { mapController = getter; }
let buildProject: (() => Promise<{project: GeoLibreProject; defaultProjectName: string}>) | null = null;
export function registerArkProjectBuilder(builder: typeof buildProject) { buildProject = builder; }

window.addEventListener('message', async event => {
    if (event.source !== window.parent || event.origin !== location.origin ||
        event.data?.source !== 'ark-workbench' || typeof event.data.id !== 'string') return;
    const {id, type, content} = event.data;
    if (!['save-project', 'open-project', 'capture-visible'].includes(type)) return;
    const reply = (payload: object) => window.parent.postMessage(
        {source: 'ark-workbench-map', type: 'workbench-result', id, ...payload}, location.origin);
    try {
        const state = useAppStore.getState();
        if (type === 'save-project') {
            if (!state.deploymentCapabilities.has('project:edit') || !buildProject) {
                throw new Error('地图编辑器暂时无法保存工程。');
            }
            const {project, defaultProjectName} = await buildProject();
            if (useAppStore.getState().projectGeneration !== state.projectGeneration) {
                throw new Error('工程已切换，请重新保存。');
            }
            const safe = redactProjectCredentials(excludeHiddenFieldsFromProject(project)).project;
            const {isUnsavableLocalRaster} = await import('@geolibre/plugins');
            const localRasters = safe.layers.filter(layer => isUnsavableLocalRaster(layer, false)).length;
            reply({value: {content: serializeProject(safe), name: defaultProjectName, localRasters}});
        } else if (type === 'open-project') {
            if (!state.deploymentCapabilities.has('project:edit') || typeof content !== 'string') {
                throw new Error('无法打开该工程。');
            }
            const project = parseProject(content);
            state.loadProject(project, null, {rememberRecent: false});
            reply({value: project.name});
        } else {
            const surface = mapController()?.getRenderSurface();
            if (!state.deploymentCapabilities.has('export:data') || !surface) {
                throw new Error('地图还未准备好，请稍后再试。');
            }
            const {compositeMapCanvas, imageBlobToDataUrl} = await import('@geolibre/map');
            const canvas = compositeMapCanvas(surface);
            const image = await new Promise<Blob>((resolve, reject) => {
                canvas.toBlob(blob => blob ? resolve(blob) : reject(new Error('无法生成地图图片。')), 'image/png');
            });
            reply({value: await imageBlobToDataUrl(image)});
        }
    } catch (error) {
        reply({error: error instanceof Error ? error.message : '操作未完成，请重试。'});
    }
});

// The host owns the floating 小舟 UI; GeoLibre owns its processing registry and
// live layer store. Only accept messages from our same-origin parent frame.
let assistant: import('./lib/assistant/agent').AssistantSession | undefined;
let activeRun: string | null = null;
window.addEventListener('message', async event => {
    if (event.source !== window.parent || event.origin !== location.origin ||
        event.data?.source !== 'ark-workbench') return;
    if (event.data.type === 'assistant-cancel') {
        if (event.data.id === activeRun) assistant?.cancel();
        return;
    }
    if (event.data.type !== 'assistant-run' || typeof event.data.id !== 'string' ||
        typeof event.data.prompt !== 'string' || event.data.prompt.length > 2000) return;
    const id = event.data.id;
    const send = (data: object) => window.parent.postMessage(
        {source: 'ark-workbench-map', type: 'assistant-event', id, ...data}, location.origin);
    if (activeRun) {
        send({event: 'error', message: '上一项任务正在收尾，请稍后重试。'});
        return;
    }
    activeRun = id;
    try {
        const {AssistantSession} = await import('./lib/assistant/agent');
        assistant ??= new AssistantSession({getMapController: () => mapController(),
            confirmCodeExecution: async () => false});
        send({event: 'start'});
        let toolCalls = 0;
        for await (const update of assistant.stream(event.data.prompt)) {
            if (update.type === 'tool' && update.phase === 'running') {
                send({event: 'update', update});
                continue;
            }
            send({event: 'update', update});
            if (update.type === 'tool' && ++toolCalls >= 16) {
                assistant.cancel();
                throw new Error('任务步骤达到上限，已停止；已生成的图层会保留。');
            }
        }
        send({event: 'done'});
    } catch (error) {
        send({event: 'error', message: error instanceof Error ? error.message : '空间分析未能完成。'});
    } finally { activeRun = null; }
});

// Keep viewport-dependent styles in sync when an original GeoLibre preset or
// an imported project changes the background. Only send the choice, never URLs.
useAppStore.subscribe((next, previous) => {
    if (next.basemapStyleUrl === previous.basemapStyleUrl) return;
    let kind = 'external', labels = true;
    try {
        const url = new URL(next.basemapStyleUrl, location.href);
        if (url.origin === location.origin && url.pathname.endsWith('/workbench/geolibre/basemap.json')) {
            const value = url.searchParams.get('kind') || 'vector';
            if (['vector', 'imagery', 'amap', 'blank'].includes(value)) kind = value;
            labels = url.searchParams.get('labels') !== '0';
        }
    } catch { /* Native blank/background styles are also valid external choices. */ }
    window.parent.postMessage({source: 'ark-workbench-map', type: 'basemap-state', kind, labels}, location.origin);
});

window.addEventListener('message', event => {
    if (event.source !== window.parent || event.origin !== window.location.origin ||
        event.data?.source !== 'ark-workbench' || event.data?.type !== 'basemap') return;
    try {
        const url = new URL(event.data.url, location.href);
        if (url.origin !== location.origin || !url.pathname.endsWith('/workbench/geolibre/basemap.json')) return;
        const store = useAppStore.getState();
        store.setBasemapStyleUrl(url.href);
        if (event.data.acknowledge === true) {
            store.setBasemapVisible(true);
            window.parent.postMessage({source: 'ark-workbench-map', type: 'basemap-applied', url: url.href}, location.origin);
        }
    } catch { /* Only a same-origin, known style resource is accepted. */ }
});
