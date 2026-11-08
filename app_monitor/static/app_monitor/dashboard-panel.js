/* Keep the data/chat boundary on clear space instead of slicing a heading. */
(() => {
    const panel = document.getElementById('detail-panel');
    const overview = document.getElementById('dashboard-overview');
    const chat = document.getElementById('ai-agent');
    const charts = panel?.querySelector('.dashboard-charts');
    const heading = panel?.querySelector('.dashboard-latest > div');
    if (!panel || !overview || !chat || !charts || !heading) return;
    let adjustment = 0, pending = false;
    const align = () => {
        pending = false;
        if (panel.classList.contains('minimized') || overview.scrollTop > 0) return;
        const boundary = chat.getBoundingClientRect().top + adjustment;
        const chart = charts.getBoundingClientRect();
        const title = heading.getBoundingClientRect();
        let target = boundary;
        // Small corrections preserve the roughly equal split. Short screens
        // still scroll their data; never enlarge the pane to fit all content.
        if (boundary > chart.top && boundary < chart.bottom + 8 && chart.bottom + 8 - boundary <= 16) {
            target = chart.bottom + 8;
        }
        if (target > title.top - 6 && target < title.bottom + 6) target = title.top - 6;
        const next = Math.max(-12, Math.min(24, boundary - target));
        if (Math.abs(next - adjustment) < .5) return;
        adjustment = next;
        panel.style.setProperty('--dashboard-split-correction', `${adjustment * 2}px`);
    };
    const schedule = () => { if (!pending) { pending = true; requestAnimationFrame(align); } };
    const observer = new ResizeObserver(schedule);
    [panel, charts, heading].forEach(element => observer.observe(element));
    overview.addEventListener('scroll', schedule, {passive:true});
    document.fonts?.ready.then(schedule);
    schedule();
})();
