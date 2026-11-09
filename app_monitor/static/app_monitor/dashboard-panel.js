/* Match the chat card to the chart edges when the overview has a scrollbar. */
(() => {
    const panel = document.getElementById('detail-panel');
    const charts = panel?.querySelector('.dashboard-charts');
    if (!charts) return;
    new ResizeObserver(([entry]) => {
        if (entry.contentRect.width > 0) {
            panel.style.setProperty('--dashboard-data-width', `${entry.contentRect.width}px`);
        }
    }).observe(charts);
})();
