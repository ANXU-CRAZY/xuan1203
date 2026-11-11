(() => {
    const form = document.getElementById('monitoring-report-form');
    if (!form) return;
    const status = document.getElementById('monitoring-report-status');
    const buttons = [...form.querySelectorAll('button[type="submit"]')];
    form.elements.month.value = Number(form.dataset.currentMonth.split('-')[1]);
    let busy = false;
    form.addEventListener('submit', async event => {
        event.preventDefault();
        if (busy || !form.reportValidity()) return;
        busy = true;
        buttons.forEach(button => { button.disabled = true; });
        status.textContent = '正在汇总观测数据、绘制图表并生成 Word，请稍候…';
        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(), 90000);
        try {
            const kind = event.submitter?.value || 'annual';
            const year = Number(form.elements.year.value);
            const month = Number(form.elements.month.value);
            const response = await fetch(form.action, {
                method:'POST',
                headers:{
                    'Content-Type':'application/json',
                    'X-CSRFToken':form.elements.csrfmiddlewaretoken.value,
                },
                body:JSON.stringify({kind, year, month}),
                signal:controller.signal,
            });
            if (!response.ok) {
                const payload = await response.json().catch(() => ({}));
                throw new Error(payload.detail || '报告生成失败，请稍后重试。');
            }
            if (!response.headers.get('Content-Type')?.includes('wordprocessingml')) {
                throw new Error('未收到有效的 Word 文档，请重试。');
            }
            const blob = await response.blob();
            const url = URL.createObjectURL(blob);
            const link = document.createElement('a');
            link.href = url;
            link.download = kind === 'annual' ? `${year}年鸟类监测年度报告.docx` : `${year}年${month}月鸟类监测月度报告.docx`;
            document.body.appendChild(link);
            link.click();
            link.remove();
            setTimeout(() => URL.revokeObjectURL(url), 30000);
            status.textContent = '';
        } catch (error) {
            status.textContent = error.name === 'AbortError' ? '报告生成超时，请稍后重试。' : error.message;
        } finally {
            clearTimeout(timer);
            busy = false;
            buttons.forEach(button => { button.disabled = false; });
        }
    });
})();
