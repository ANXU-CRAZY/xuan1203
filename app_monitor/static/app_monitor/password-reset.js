(() => {
    const section = document.getElementById('password-reset');
    const form = document.getElementById('resetForm');
    const email = document.getElementById('resetEmail');
    const code = document.getElementById('resetCode');
    const password = document.getElementById('resetPassword');
    const confirmation = document.getElementById('resetConfirmation');
    const fields = document.getElementById('resetFields');
    const send = document.getElementById('resetSend');
    const confirm = document.getElementById('resetConfirm');
    const status = document.getElementById('resetStatus');
    const deadlines = new Map();
    let busy = false;
    let completed = false;

    function showStatus(message, error = false) {
        status.textContent = message;
        status.className = message ? `message ${error ? 'error' : 'success'}` : 'message';
    }

    function showFields(show) {
        fields.hidden = !show;
        fields.disabled = !show;
    }

    function updateButtons() {
        const deadline = deadlines.get(email.value.trim().toLowerCase()) || 0;
        const remaining = Math.max(0, Math.ceil((deadline - Date.now()) / 1000));
        send.disabled = busy || completed || remaining > 0;
        confirm.disabled = busy || completed;
        send.textContent = remaining ? `${remaining} 秒后可重发` : fields.hidden ? '发送验证码' : '重新发送验证码';
    }

    function switchView() {
        const open = location.hash === '#password-reset';
        section.hidden = !open;
        for (const id of ['loginTabs', 'loginSection', 'registerSection', 'msgBox']) {
            document.getElementById(id).hidden = open;
        }
        if (open) email.focus();
        else {
            form.reset();
            showFields(false);
            showStatus('');
        }
        updateButtons();
    }

    email.addEventListener('input', () => {
        showFields(false);
        showStatus('');
        code.value = '';
        password.value = '';
        confirmation.value = '';
        updateButtons();
    });
    const digits = value => value.replace(/[^0-9]/g, '').slice(0, 6);
    code.addEventListener('input', () => { code.value = digits(code.value); });
    code.addEventListener('paste', event => {
        event.preventDefault();
        code.value = digits(event.clipboardData.getData('text'));
        if (code.value.length === 6) password.focus();
    });

    async function submit(requesting) {
        if (busy || completed || (requesting && send.disabled) || !email.reportValidity()) return;
        const address = email.value.trim().toLowerCase();
        const payload = {email: address};
        if (!requesting) {
            if (!form.reportValidity()) return;
            if (password.value !== confirmation.value) {
                showStatus('两次输入的密码不一致。', true);
                confirmation.focus();
                return;
            }
            Object.assign(payload, {code: code.value, new_password: password.value, confirm_password: confirmation.value});
        }
        busy = true;
        email.readOnly = true;
        updateButtons();
        showStatus(requesting ? '正在提交验证码请求…' : '正在验证并修改密码…');
        try {
            const response = await fetch(requesting ? form.dataset.sendUrl : form.dataset.confirmUrl, {
                method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload),
            });
            const result = await response.json();
            if (requesting && result.retry_after) deadlines.set(address, Date.now() + result.retry_after * 1000);
            if (!response.ok) {
                const messages = result.detail || result.new_password || result.code || result.email;
                showStatus([messages || '请求失败，请稍后重试。'].flat().join(' '), true);
                return;
            }
            if (requesting) {
                showFields(true);
                code.value = '';
                code.focus();
                showStatus(`${result.detail}未收到邮件时，可查看垃圾邮件或在倒计时结束后重试。`);
            } else {
                completed = true;
                form.reset();
                showFields(false);
                localStorage.removeItem('yb_token');
                localStorage.removeItem('yb_user');
                showStatus('密码修改成功，正在返回登录页。');
                setTimeout(() => location.replace(form.dataset.loginUrl), 1400);
            }
        } catch {
            showStatus('暂时无法连接服务器，请稍后重试。', true);
        } finally {
            busy = false;
            email.readOnly = completed;
            updateButtons();
        }
    }

    send.addEventListener('click', () => submit(true));
    form.addEventListener('submit', event => {
        event.preventDefault();
        submit(fields.hidden);
    });

    window.addEventListener('hashchange', switchView);
    switchView();
    setInterval(updateButtons, 1000);
})();
