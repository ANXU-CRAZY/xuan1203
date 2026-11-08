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
