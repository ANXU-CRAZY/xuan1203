/* Small game utilities. Storage restrictions must never stop a game starting. */
window.ArkGameStorage = (() => {
    const memory = new Map();
    return {
        getItem(key) {
            try { return window.localStorage.getItem(key) ?? memory.get(key) ?? null; }
            catch (_) { return memory.get(key) ?? null; }
        },
        setItem(key, value) {
            memory.set(key, String(value));
            try { window.localStorage.setItem(key, String(value)); } catch (_) { /* Play for this session. */ }
        },
        readObject(key) {
            try {
                const data = JSON.parse(this.getItem(key) || '{}');
                return data && typeof data === 'object' && !Array.isArray(data) ? data : {};
            } catch (_) { return {}; }
        }
    };
})();
