/* Drag a card without triggering its normal click-to-toggle action. */
document.querySelectorAll('.dashboard-widget').forEach(card => {
    let gesture = null;
    let suppressClick = false;
    const place = (left, top) => {
        const toolbarBottom = document.querySelector('.top-beam')?.getBoundingClientRect().bottom || 0;
        const inset = 8;
        card.style.position = 'fixed';
        card.style.left = `${Math.max(inset, Math.min(left, innerWidth - card.offsetWidth - inset))}px`;
        card.style.top = `${Math.max(toolbarBottom + inset, Math.min(top, innerHeight - card.offsetHeight - inset))}px`;
    };
    card.addEventListener('pointerdown', event => {
        if (!event.isPrimary || event.button !== 0) return;
        const rect = card.getBoundingClientRect();
        gesture = { id:event.pointerId, x:event.clientX, y:event.clientY, left:rect.left, top:rect.top };
        suppressClick = false;
        card.setPointerCapture(event.pointerId);
    });
    card.addEventListener('pointermove', event => {
        if (gesture?.id !== event.pointerId) return;
        const dx = event.clientX - gesture.x, dy = event.clientY - gesture.y;
        if (!suppressClick && Math.hypot(dx, dy) < 6) return;
        suppressClick = true;
        card.classList.add('is-dragging');
        place(gesture.left + dx, gesture.top + dy);
    });
    const finish = event => {
        if (gesture?.id !== event.pointerId) return;
        gesture = null;
        card.classList.remove('is-dragging');
    };
    card.addEventListener('pointerup', finish);
    card.addEventListener('lostpointercapture', finish);
    card.addEventListener('click', event => {
        if (!suppressClick || event.detail === 0) return;
        event.preventDefault();
        event.stopImmediatePropagation();
        suppressClick = false;
    }, true);
    window.addEventListener('resize', () => {
        if (card.style.position !== 'fixed') return;
        place(parseFloat(card.style.left), parseFloat(card.style.top));
    });
});

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
        if (panel.classList.contains('dashboard-closed') || panel.classList.contains('dashboard-single')) return;
        const chartWidth = charts.getBoundingClientRect().width;
        if (chartWidth > 0 && panel.style.getPropertyValue('--dashboard-data-width') !== `${chartWidth}px`) {
            panel.style.setProperty('--dashboard-data-width', `${chartWidth}px`);
        }
        if (overview.scrollTop > 0) return;
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
