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

    // Align the controls with the top of the compact monitoring panel.
    const controls = document.querySelector('.dashboard-module-controls');
    const overview = document.getElementById('dashboard-overview');
    const alignControls = () => {
        if (!panel.classList.contains('dashboard-single') || overview.hidden) return;
        controls.style.setProperty('--dashboard-panel-top', `${panel.getBoundingClientRect().top}px`);
    };
    new ResizeObserver(alignControls).observe(panel);
    new MutationObserver(alignControls).observe(panel, {attributeFilter:['class', 'style']});
    window.addEventListener('resize', alignControls);
})();
