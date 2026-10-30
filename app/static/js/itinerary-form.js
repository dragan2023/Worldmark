(() => {
  const form = document.querySelector('#itinerary-form');
  if (!form) return;
  const selected = new Map();
  const error = document.querySelector('#form-error');
  const dialog = document.querySelector('#landmark-dialog');
  const options = document.querySelector('#landmark-options');
  const summary = document.querySelector('#selected-landmarks');
  const enhancement = document.querySelector('#use-enhancement');
  const button = document.querySelector('#preview-button');
  const pageInfo = document.querySelector('#landmark-page-info');
  const prevButton = document.querySelector('#landmark-prev');
  const nextButton = document.querySelector('#landmark-next');
  const keywordInput = document.querySelector('#landmark-keyword');
  const parseError = window.apiErrors ? window.apiErrors.parse : (body => (body && body.detail) || '请求失败');

  const PAGE_SIZE = 50;
  let page = 1;
  let totalPages = 1;
  let lastQuery = '';
  let submitting = false;
  let requestToken = 0;

  const preselectEl = document.querySelector('#preselect-landmark');
  if (preselectEl) {
    try {
      const item = JSON.parse(preselectEl.textContent);
      if (item && item.id) selected.set(item.id, item);
    } catch (_) { /* 忽略非法预选数据 */ }
  }

  const updateSummary = () => {
    if (!selected.size) {
      summary.textContent = '尚未选择地标';
      return;
    }
    summary.textContent = '';
    [...selected.values()].forEach(item => {
      const chip = document.createElement('span');
      chip.className = 'selected-chip';
      chip.textContent = `${item.name}（${item.city}）`;
      const remove = document.createElement('button');
      remove.type = 'button';
      remove.className = 'chip-remove';
      remove.setAttribute('aria-label', `移除 ${item.name}`);
      remove.textContent = '×';
      remove.addEventListener('click', () => {
        selected.delete(item.id);
        updateSummary();
      });
      chip.appendChild(remove);
      summary.appendChild(chip);
    });
  };

  const loadLandmarks = async (targetPage = 1) => {
    const keyword = keywordInput.value.trim();
    if (keyword !== lastQuery) { lastQuery = keyword; targetPage = 1; }
    const token = ++requestToken; // 只接受最后一次请求的结果，避免慢响应覆盖新查询
    options.textContent = '正在加载…';
    const params = new URLSearchParams({ page_size: String(PAGE_SIZE), page: String(targetPage), country: 'CN' });
    if (keyword) params.set('q', keyword);
    try {
      const response = await fetch(`/api/v1/landmarks?${params}`, { credentials: 'same-origin' });
      const data = await response.json().catch(() => ({}));
      if (token !== requestToken) return;
      if (!response.ok) { options.textContent = parseError(data) || '无法加载地标，请稍后重试。'; return; }
      page = data.page || targetPage;
      totalPages = Math.max(1, Math.ceil((data.total || 0) / PAGE_SIZE));
      if (pageInfo) pageInfo.textContent = `第 ${page} / ${totalPages} 页 · 共 ${data.total || 0} 个`;
      if (prevButton) prevButton.disabled = page <= 1;
      if (nextButton) nextButton.disabled = page >= totalPages;
      if (!data.items.length) { options.textContent = '没有匹配的地标，换个关键词试试。'; return; }
      options.replaceChildren(...data.items.map(item => {
        const label = document.createElement('label');
        label.className = 'landmark-option';
        const input = document.createElement('input');
        input.type = 'checkbox';
        input.checked = selected.has(item.id);
        input.addEventListener('change', () => {
          if (input.checked) {
            selected.set(item.id, { id: item.id, name: item.name, city: item.city_name || item.province_name || '国内' });
          } else {
            selected.delete(item.id);
          }
          updateSummary();
        });
        const text = document.createElement('span');
        text.textContent = `${item.name} · ${item.work_title} · ${item.city_name || item.province_name || ''}`;
        label.append(input, text);
        return label;
      }));
    } catch (exception) {
      if (token === requestToken) options.textContent = '网络异常，无法加载地标列表。';
    }
  };

  document.querySelector('#open-landmark-picker').addEventListener('click', () => {
    dialog.showModal();
    lastQuery = keywordInput.value.trim();
    loadLandmarks(1);
  });
  document.querySelector('#close-landmark-picker').addEventListener('click', () => dialog.close());
  document.querySelector('#confirm-landmarks').addEventListener('click', () => { updateSummary(); dialog.close(); });
  document.querySelector('#landmark-search-button').addEventListener('click', () => loadLandmarks(1));
  keywordInput.addEventListener('keydown', event => {
    if (event.key === 'Enter') { event.preventDefault(); loadLandmarks(1); }
  });
  if (prevButton) prevButton.addEventListener('click', () => loadLandmarks(page - 1));
  if (nextButton) nextButton.addEventListener('click', () => loadLandmarks(page + 1));

  updateSummary();

  form.addEventListener('submit', async event => {
    event.preventDefault();
    if (submitting) return; // 防重复提交
    error.textContent = '';
    if (!selected.size) {
      error.textContent = '请至少选择一个必去 IP 地标。';
      document.querySelector('#open-landmark-picker').focus();
      return;
    }
    const startDate = form.elements.start_date.value;
    const endDate = form.elements.end_date.value;
    if (startDate && endDate && endDate < startDate) {
      error.textContent = '结束日期不能早于开始日期。';
      form.elements.end_date.focus();
      return;
    }
    if (startDate && endDate) {
      const days = (new Date(endDate) - new Date(startDate)) / 86400000 + 1;
      if (days > 30) {
        error.textContent = '单次行程最多 30 天，请缩短日期范围或拆分规划。';
        form.elements.end_date.focus();
        return;
      }
    }

    const data = Object.fromEntries(new FormData(form).entries());
    delete data.use_enhancement;
    data.must_visit_landmark_ids = [...selected.keys()];
    data.interests = [...form.querySelectorAll('[name="interests"]:checked')].map(item => item.value);
    data.auto_fill_nearby = Boolean(form.elements.auto_fill_nearby && form.elements.auto_fill_nearby.checked);
    data.traveler_count = Number(data.traveler_count);
    if (data.budget_amount) data.budget_amount = Number(data.budget_amount); else delete data.budget_amount;
    Object.keys(data).forEach(key => { if (data[key] === '') delete data[key]; });

    const enhanced = Boolean(enhancement && enhancement.checked);
    const endpoint = enhanced ? '/api/v1/itineraries/finalize' : '/api/v1/itineraries';
    submitting = true;
    button.disabled = true;
    button.textContent = enhanced ? '正在调用外部服务增强行程（可能需要 1–2 分钟）…' : '正在生成基础行程…';
    try {
      const response = await fetch(endpoint, {
        method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data),
      });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) {
        const detail = body && body.detail;
        if (detail && typeof detail === 'object' && detail.fallback) {
          throw new Error(`${detail.message || '外部增强不可用'}。${detail.fallback}`);
        }
        throw new Error(parseError(body) || `生成失败（${response.status}）`);
      }
      location.assign(`/itineraries/${body.id}`);
    } catch (exception) {
      error.textContent = enhanced
        ? `${exception.message} 可取消「外部行程增强」改用基础规划。`
        : exception.message;
      submitting = false;
      button.disabled = false;
      button.textContent = '生成标准行程';
    }
  });
})();
