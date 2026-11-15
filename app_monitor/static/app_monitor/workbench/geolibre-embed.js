/** Current GeoLibre iframe protocol version. Version 1 requests remain supported by the app. */
export const EMBED_API_VERSION = 2;
export const EMBED_API_SOURCE = "geolibre";
function validOrigin(value) {
    const origin = new URL(value).origin;
    if (origin === "null")
        throw new Error("origin must be an http(s) origin");
    return origin;
}
/** Connect to a framed GeoLibre app and wait until its embed API is ready. */
export function connect(iframe, options) {
    // Every failure leaves through the returned promise, including this one:
    // `validOrigin` throws synchronously, and a caller writing
    // `connect(iframe, opts).catch(...)` — the shape the `Promise` return type
    // invites — would never see it, because the throw happens before `.catch` is
    // attached.
    let origin;
    try {
        origin = validOrigin(options.origin);
    }
    catch (error) {
        return Promise.reject(error instanceof Error ? error : new Error(String(error)));
    }
    const target = iframe.contentWindow;
    if (!target)
        return Promise.reject(new Error("The iframe has no contentWindow"));
    let sequence = 0;
    let disconnected = false;
    const pending = new Map();
    const listeners = new Map();
    const send = (type, payload = {}) => {
        if (disconnected)
            return Promise.reject(new Error("The GeoLibre client is disconnected"));
        const requestId = `geolibre-${Date.now()}-${++sequence}`;
        target.postMessage({ v: EMBED_API_VERSION, type, payload, requestId }, origin);
        return new Promise((resolve, reject) => {
            const timer = window.setTimeout(() => {
                pending.delete(requestId);
                reject(new Error(`Timed out waiting for a response to "${type}"`));
            }, options.requestTimeoutMs ?? 15_000);
            pending.set(requestId, {
                resolve: (value) => {
                    window.clearTimeout(timer);
                    resolve(value);
                },
                reject: (reason) => {
                    window.clearTimeout(timer);
                    reject(reason);
                },
            });
        });
    };
    let readyResolve = null;
    let readyReject = null;
    const ready = new Promise((resolve, reject) => {
        readyResolve = resolve;
        readyReject = reject;
    });
    const client = {
        loadProject: (url) => send("loadProject", { url }),
        setView: (target) => send("setView", target),
        highlightFeature: (payload) => send("highlightFeature", payload),
        openTool: (id, params = {}) => send("openTool", { id, params }),
        setLayerVisibility: (layerId, visible) => send("setLayerVisibility", { layerId, visible }),
        listLayers: () => send("listLayers"),
        setFilter: (layerId, expression) => send("setFilter", { layerId, expression }),
        setRenderer: (renderer) => send("setRenderer", { renderer }),
        getRenderer: () => send("getRenderer"),
        getViewport: () => send("getViewport"),
        addLayer: (spec) => send("addLayer", { spec }),
        addData: (url, options = {}) => send("addData", { url, ...options }),
        exportImage: () => send("exportImage"),
        getLayerFeatures: (layerId) => send("getLayerFeatures", { layerId }),
        getDrawnFeatures: () => send("getDrawnFeatures", {}),
        on: (type, listener) => {
            const set = listeners.get(type) ?? new Set();
            set.add(listener);
            listeners.set(type, set);
            return () => set.delete(listener);
        },
        disconnect: () => {
            if (disconnected)
                return;
            disconnected = true;
            window.removeEventListener("message", receive);
            for (const request of pending.values())
                request.reject(new Error("Client disconnected"));
            pending.clear();
            listeners.clear();
        },
    };
    const receive = (event) => {
        if (event.source !== target || event.origin !== origin)
            return;
        const data = event.data;
        if (!data || data.source !== EMBED_API_SOURCE || data.v !== EMBED_API_VERSION)
            return;
        const type = data.type;
        const payload = (data.payload ?? {});
        if (type === "ack") {
            // Settling the command promise is the ack's job, but it stays an event
            // too: `ack` is a key of `EmbedEventMap`, so `on("ack", …)` type-checks
            // and has to fire — including for an ack with no pending request, which
            // is exactly the case a host would subscribe to see.
            const requestId = typeof payload.requestId === "string" ? payload.requestId : null;
            const request = requestId ? pending.get(requestId) : undefined;
            if (requestId && request) {
                pending.delete(requestId);
                if (payload.ok === true)
                    request.resolve(payload.result);
                else
                    request.reject(new Error(String(payload.error ?? "GeoLibre request failed")));
            }
        }
        else if (type === "ready") {
            readyResolve?.(client);
        }
        for (const listener of listeners.get(type) ?? [])
            listener(payload);
    };
    window.addEventListener("message", receive);
    const timer = window.setTimeout(() => {
        client.disconnect();
        readyReject?.(new Error("Timed out waiting for GeoLibre"));
    }, options.timeoutMs ?? 15_000);
    return ready.finally(() => window.clearTimeout(timer));
}
