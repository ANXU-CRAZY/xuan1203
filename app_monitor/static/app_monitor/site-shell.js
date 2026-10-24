/* Shared public-site navigation; no dependency on the monitoring API. */
(() => {
    const button = document.getElementById('games-toggle');
    const panel = document.getElementById('games-panel');
    if (button && panel) {
        const positionPanel = () => {
            const header = document.querySelector('.top-beam').getBoundingClientRect();
            const anchor = button.getBoundingClientRect();
            const left = Math.max(12, Math.min(anchor.left, innerWidth - panel.offsetWidth - 12));
            panel.style.left = `${left}px`;
            panel.style.top = `${header.bottom + 8}px`;
            panel.style.maxHeight = `${Math.max(80, innerHeight - header.bottom - 28)}px`;
        };
        const close = (restoreFocus = false) => {
            panel.hidden = true;
            button.setAttribute('aria-expanded', 'false');
            if (restoreFocus) button.focus();
        };
        button.addEventListener('click', () => {
            if (!panel.hidden) { close(); return; }
            panel.hidden = false;
            button.setAttribute('aria-expanded', 'true');
            positionPanel();
        });
        document.getElementById('games-close').addEventListener('click', () => close(true));
        document.addEventListener('pointerdown', event => {
            if (!panel.hidden && !panel.contains(event.target) && !button.contains(event.target)) close();
        });
        document.addEventListener('keydown', event => {
            if (event.key === 'Escape' && !panel.hidden) { event.preventDefault(); close(true); }
            else if (event.key === 'ArrowDown' && event.target === button && !panel.hidden) {
                event.preventDefault(); panel.querySelector('a').focus();
            } else if (event.key === 'Tab' && !panel.hidden) {
                const links = [...panel.querySelectorAll('button, a')];
                if (event.target === button && !event.shiftKey) {
                    event.preventDefault(); links[0].focus();
                } else if (event.target === links.at(-1) && !event.shiftKey) {
                    event.preventDefault(); close(true);
                } else if (event.target === links[0] && event.shiftKey) {
                    event.preventDefault(); close(true);
                }
            }
        });
        document.addEventListener('focusin', event => {
            if (!panel.hidden && event.target !== button && !panel.contains(event.target)) close();
        });
        window.addEventListener('resize', () => { if (!panel.hidden) positionPanel(); });
    }
    if (window.Chart) {
        const style = getComputedStyle(document.documentElement);
        Chart.defaults.font.family = style.getPropertyValue('--ark-sans').trim();
        Chart.defaults.color = '#687A80';
    }
})();
