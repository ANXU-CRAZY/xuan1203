(() => {
    const dialog = document.getElementById('recognition-choice');
    if (!dialog || !dialog.showModal) return;
    let trigger;
    document.querySelectorAll('[data-recognition-choice]').forEach(link => {
        link.addEventListener('click', event => {
            if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
            event.preventDefault();
            trigger = link;
            dialog.showModal();
        });
    });
    dialog.querySelector('.recognition-close').addEventListener('click', () => dialog.close());
    dialog.addEventListener('click', event => {
        if (event.target !== dialog) return;
        const rect = dialog.getBoundingClientRect();
        if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) dialog.close();
    });
    dialog.addEventListener('close', () => trigger?.focus());
})();
