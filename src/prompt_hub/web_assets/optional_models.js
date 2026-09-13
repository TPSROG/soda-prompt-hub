(() => {
  const dialog = document.querySelector('#optionalModelsDialog');
  const list = document.querySelector('#optionalModelsList');
  const notice = document.querySelector('#optionalModelsNotice');
  let data = null, timer = null, fetching = false, highlighted = '', returnFocus = null, rendered = '';
  const pending = new Map();
  const escape = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  const size = bytes => `${(Number(bytes || 0) / 1000000).toFixed(1)} MB`;
  async function request(url, options) {
    const response = await fetch(url, {signal: AbortSignal.timeout(10000), ...options});
    const body = await response.json();
    if (!response.ok) throw new Error(typeof body.detail === 'string' ? body.detail : `请求失败（${response.status}）`);
    return body;
  }
  function message(text, error = false) { notice.textContent = text; notice.dataset.error = String(error); }
  function render() {
    if (!data) return;
    const signature = JSON.stringify([data, [...pending], highlighted]);
    if (signature === rendered) return;
    rendered = signature;
    document.querySelector('#optionalModelsHost').textContent = `安装到 ${data.host} · WebUI 服务所在设备`;
    document.querySelector('#optionalModelsRoot').textContent = data.models_root;
    const focused = document.activeElement?.id;
    const expanded = new Set([...list.querySelectorAll('details[open]')].map(item => item.dataset.modelDetails));
    list.innerHTML = data.models.map((model, index) => {
      const job = model.job, active = job && ['queued','running'].includes(job.status);
      const stage = pending.has(model.id) ? 'pending' : active ? job.status : model.state === 'ready' ? 'ready' : job?.status === 'failed' ? 'failed' : job?.status === 'canceled' ? 'canceled' : model.state;
      const labels = {missing:'未安装',partial:'待继续',unverified:'待校验',ready:'可用',queued:'排队中',running:'安装中',failed:'未完成',canceled:'已取消',blocked:'路径不可用',pending:'处理中'};
      const detail = pending.get(model.id) || (active ? (job.cancel_requested ? '正在取消，等待当前网络读取或自检结束…' : job.progress_message || '等待后台任务开始…') : stage === 'failed' ? job.error : stage === 'canceled' ? '下载已取消，已下载的部分会保留，可继续安装。' : model.reason);
      const total = Number(job?.progress_total) || model.size_bytes;
      const current = Math.min(total, Number(job?.progress_current) || 0);
      const progress = active && job.status === 'running' ? `<progress class="model-install-progress" aria-label="${escape(model.title)}下载进度" value="${current}" max="${total}"></progress><p>${size(current)} / ${size(total)} · ${Math.floor(current / total * 100)}%${current === total ? '，正在完成校验' : ''}</p>` : '';
      const action = active ? 'cancel' : 'install';
      const text = active ? (job.cancel_requested ? '正在取消…' : '取消安装') : stage === 'ready' ? '已安装 · 可使用' : stage === 'unverified' ? '校验并启用' : ['failed','canceled','partial'].includes(stage) ? '重试 / 继续安装' : '下载并安装';
      const disabled = pending.has(model.id) || stage === 'ready' || stage === 'blocked' || Boolean(active && job.cancel_requested);
      return `<article class="model-install-card" data-state="${stage}" data-highlight="${model.id === highlighted}"><div class="model-install-card-top"><span class="model-install-number">0${index + 1}</span><span class="model-install-badge">${labels[stage] || stage}</span></div><h3>${escape(model.title)}</h3><p class="model-install-purpose">${escape(model.purpose)}</p><div class="model-install-size">${size(model.size_bytes)}<small>完整下载</small></div><div class="model-install-feedback" role="status" aria-live="polite"><p>${escape(detail)}</p>${progress}</div><details data-model-details="${escape(model.id)}" ${expanded.has(model.id) ? 'open' : ''}><summary>来源、文件与安装位置</summary><a href="${escape(model.source_url)}" target="_blank" rel="noopener noreferrer">查看模型来源与许可 ↗</a><code>${escape(model.files.join(' + '))}</code><code>${escape(model.path)}</code><p>已锁定版本 ${escape(model.revision.slice(0,12))}，下载后核对 SHA-256。手动安装请从此固定版本取文件。</p></details><div class="model-install-actions"><button id="optional-action-${escape(model.id)}" type="button" data-model-action="${action}" data-model-id="${escape(model.id)}" ${disabled ? 'disabled' : ''} aria-busy="${pending.has(model.id)}">${text}</button></div></article>`;
    }).join('');
    if (focused?.startsWith('optional-action-')) document.getElementById(focused)?.focus({preventScroll:true});
  }
  async function refresh() {
    if (fetching || !dialog.open) return;
    fetching = true;
    try {
      const previous = data;
      data = await request('/api/optional-models');
      if (dialog.open) {
        render();
        const finished = data.models.find(model => {
          const before = previous?.models.find(item => item.id === model.id)?.job;
          return before && ['queued','running'].includes(before.status) && ['completed','failed','canceled'].includes(model.job?.status);
        });
        if (finished) message(finished.job.status === 'completed' ? `${finished.title}已安装并通过自检，可以使用。` : finished.job.status === 'canceled' ? '已取消安装，断点已保留。需要时可继续。' : `${finished.title}安装未完成，请查看卡片中的原因并重试。`, finished.job.status === 'failed');
        else if (notice.textContent.startsWith('无法读取安装状态')) message('连接已恢复，已显示最新安装状态。');
      }
    }
    catch (error) { message(`无法读取安装状态：${error.message}。稍后会自动重试。`, true); }
    finally { fetching = false; clearTimeout(timer); if (dialog.open) timer = setTimeout(refresh, 1200); }
  }
  window.openOptionalModels = async (modelId = '') => {
    highlighted = typeof modelId === 'string' ? modelId : '';
    if (!dialog.open) { returnFocus = document.activeElement; dialog.showModal(); }
    message(highlighted ? '当前功能需要此本地模型。请选择安装，或关闭窗口暂时跳过。' : '三个模型都可跳过。选择一项，即开始下载、校验与本机自检。');
    render();
    await refresh();
  };
  window.ensureLocalTagger = async (modelId) => {
    const config = await request('/api/tagger-config');
    const selected = modelId || config.id;
    if (config.models.some(model => model.id === selected && model.available)) return true;
    await window.openOptionalModels(selected);
    return false;
  };
  list.addEventListener('click', async event => {
    const button = event.target.closest('[data-model-action]');
    if (!button || button.disabled) return;
    const id = button.dataset.modelId, model = data?.models.find(item => item.id === id);
    if (!model || pending.has(id)) return;
    const cancel = button.dataset.modelAction === 'cancel';
    pending.set(id, cancel ? '正在请求取消…' : '正在创建安装任务…'); render();
    try {
      await request(cancel ? `/api/jobs/${encodeURIComponent(model.job.job_id)}/cancel` : `/api/optional-models/${encodeURIComponent(id)}/install`, {method:'POST'});
      message(cancel ? '已请求取消。网络读取或本机自检结束后会停止，断点保留。' : '安装任务已提交。可以留在这里查看进度，也可以关闭窗口继续工作。');
    } catch (error) { message(`操作失败：${error.message}`, true); }
    finally { pending.delete(id); render(); await refresh(); }
  });
  document.addEventListener('click', event => {
    const button = event.target.closest('[data-open-optional-models]');
    if (button) window.openOptionalModels(button.dataset.openOptionalModels);
  });
  document.querySelector('#optionalModelsClose').addEventListener('click', () => dialog.close());
  dialog.addEventListener('close', () => { clearTimeout(timer); if (returnFocus?.isConnected) returnFocus.focus({preventScroll:true}); window.dispatchEvent(new Event('optional-models-changed')); });
  document.querySelector('#optionalModelsServices').addEventListener('click', () => { dialog.close(); window.openModelEndpoints?.(); });
})();
