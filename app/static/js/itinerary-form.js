(() => {
  const form = document.querySelector('#itinerary-form');
  const selected = new Map();
  const error = document.querySelector('#form-error');
  const dialog = document.querySelector('#landmark-dialog');
  const options = document.querySelector('#landmark-options');
  const summary = document.querySelector('#selected-landmarks');

  const readJson = async response => {
    const text = await response.text();
    try { return text ? JSON.parse(text) : {}; } catch (_) { return {}; }
  };
  const updateSummary = () => {
    summary.textContent = selected.size
      ? [...selected.values()].map(item => `${item.name}（${item.city}）`).join('、')
      : '尚未选择地标';
  };
  const loadLandmarks = async () => {
    options.textContent = '正在加载…';
    const keyword = document.querySelector('#landmark-keyword').value.trim();
    const params = new URLSearchParams({ page_size: '50', country: 'CN' });
    if (keyword) params.set('q', keyword);
    const response = await fetch(`/api/v1/landmarks?${params}`, { credentials: 'same-origin' });
    const data = await readJson(response);
    if (!response.ok) { options.textContent = '无法加载地标'; return; }
    options.replaceChildren(...data.items.map(item => {
      const label = document.createElement('label');
      label.className = 'landmark-option';
      const input = document.createElement('input');
      input.type = 'checkbox';
      input.checked = selected.has(item.id);
      input.onchange = () => input.checked
        ? selected.set(item.id, { id: item.id, name: item.name, city: item.city_name || item.province_name || '国内' })
        : selected.delete(item.id);
      const text = document.createElement('span');
      text.textContent = `${item.name} · ${item.work_title} · ${item.city_name || item.province_name || ''}`;
      label.append(input, text);
      return label;
    }));
  };

  document.querySelector('#open-landmark-picker').onclick = () => { dialog.showModal(); loadLandmarks(); };
  document.querySelector('#close-landmark-picker').onclick = () => dialog.close();
  document.querySelector('#confirm-landmarks').onclick = () => { updateSummary(); dialog.close(); };
  document.querySelector('#landmark-search-button').onclick = loadLandmarks;

  form.onsubmit = async event => {
    event.preventDefault();
    error.textContent = '';
    if (!selected.size) { error.textContent = '请至少选择一个必去 IP 地标。'; return; }
    const data = Object.fromEntries(new FormData(form).entries());
    data.must_visit_landmark_ids = [...selected.keys()];
    data.interests = [...form.querySelectorAll('[name="interests"]:checked')].map(item => item.value);
    data.auto_fill_nearby = form.elements.auto_fill_nearby.checked;
    data.traveler_count = Number(data.traveler_count);
    if (data.budget_amount) data.budget_amount = Number(data.budget_amount); else delete data.budget_amount;
    Object.keys(data).forEach(key => { if (data[key] === '') delete data[key]; });
    const button = document.querySelector('#preview-button');
    button.disabled = true;
    button.textContent = '正在规划行程并核算预算（通常需要 1–2 分钟）…';
    try {
      const response = await fetch('/api/v1/itineraries/finalize', {
        method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data),
      });
      const itinerary = await readJson(response);
      if (!response.ok) throw new Error(itinerary.detail || `生成失败（${response.status}）`);
      location.assign(`/itineraries/${itinerary.id}`);
    } catch (exception) {
      error.textContent = exception.message;
      button.disabled = false;
      button.textContent = '生成标准行程';
    }
  };
})();
