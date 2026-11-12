(() => {
    const dialog = document.getElementById('account-login-dialog');
    if (!dialog || typeof dialog.showModal !== 'function') return;
    document.querySelectorAll('.account-avatar').forEach(link => {
        link.addEventListener('click', event => {
            // Existing token holders restore their session through /account/.
            if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey || event.button !== 0) return;
            try {
                if (localStorage.getItem('yb_token')) return;
            } catch { /* The chooser also works when browser storage is unavailable. */ }
            event.preventDefault();
            if (!dialog.open) dialog.showModal();
        });
    });
    dialog.querySelector('.account-choice-close').addEventListener('click', () => dialog.close());
    dialog.addEventListener('click', event => {
        if (event.target !== dialog) return;
        const bounds = dialog.getBoundingClientRect();
        if (event.clientX < bounds.left || event.clientX > bounds.right ||
            event.clientY < bounds.top || event.clientY > bounds.bottom) dialog.close();
    });
})();
