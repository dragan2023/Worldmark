(() => {
  const element = document.getElementById('landmark-map');
  if (!element || !window.L) return;

  const escapeHtml = (value) => String(value).replace(/[&<>'"]/g, (character) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' })[character]);

  const colorByType = { literature: '#0b5c63', game: '#b4552d', screen: '#2f6b9c' };
  const typeLabel = { literature: '文学', game: '游戏', screen: '影视' };

  const searchInput = document.getElementById('map-locate-search');
  const resetButton = document.getElementById('map-locate-reset');
  const listElement = document.getElementById('map-locate-list');

  // 开启滚轮缩放
  const map = L.map(element, { scrollWheelZoom: true, wheelPxPerZoomLevel: 120 });
  L.tileLayer(element.dataset.tileUrl, { maxZoom: 18, attribution: '© OpenStreetMap contributors' }).addTo(map);

  // 内联 SVG 图钉（按门类配色），不依赖 Leaflet 默认图标图片
  const pinIcon = (color) => L.divIcon({
    className: 'map-pin',
    html: `<svg viewBox="0 0 24 24" width="30" height="30" aria-hidden="true"><path d="M12 2C7.58 2 4 5.58 4 10c0 5.25 8 12 8 12s8-6.75 8-12c0-4.42-3.58-8-8-8z" fill="${color}" stroke="#ffffff" stroke-width="1.5"/><circle cx="12" cy="10" r="3" fill="#ffffff"/></svg>`,
    iconSize: [30, 30],
    iconAnchor: [15, 30],
    popupAnchor: [0, -28],
  });

  let markerGroup = null;
  const itemEntries = new Map(); // id -> { marker, item, listItem }
  const groups = []; // { key, workTitle, ipType, color, itemIds }

  const showEmpty = (message) => {
    if (!listElement) return;
    const item = document.createElement('li');
    item.className = 'map-locate-empty';
    item.textContent = message;
    listElement.appendChild(item);
  };

  const allLatLngs = () => [...itemEntries.values()].map(({ item }) => [item.latitude, item.longitude]);

  const resetView = () => {
    const latlngs = allLatLngs();
    if (latlngs.length) map.fitBounds(L.latLngBounds(latlngs).pad(0.16));
  };

  fetch(element.dataset.apiUrl, { credentials: 'same-origin' })
    .then((response) => response.ok ? response.json() : Promise.reject(new Error('地图数据暂不可用')))
    .then(({ items }) => {
      if (!items.length) { map.setView([35.8617, 104.1954], 4); showEmpty('当前筛选下暂无地标点位。'); return; }

      markerGroup = L.featureGroup();
      const byKey = new Map();

      items.forEach((item) => {
        const color = colorByType[item.ip_type] || '#0b5c63';
        const marker = L.marker([item.latitude, item.longitude], { icon: pinIcon(color) })
          .bindPopup(`<strong>${escapeHtml(item.name)}</strong><br>${escapeHtml(item.work_title)}<br><a href="${escapeHtml(item.detail_url)}">查看详情</a>`)
          .addTo(markerGroup);
        itemEntries.set(String(item.id), { marker, item, listItem: null });

        const key = `${item.ip_type}:${item.work_title}`;
        if (!byKey.has(key)) {
          byKey.set(key, { key, workTitle: item.work_title, ipType: item.ip_type, color, itemIds: [] });
        }
        byKey.get(key).itemIds.push(String(item.id));
      });
      markerGroup.addTo(map);
      map.fitBounds(markerGroup.getBounds().pad(0.16));

      // 按作品分组渲染侧栏
      if (listElement) {
        byKey.forEach((group) => {
          const groupEl = document.createElement('li');
          groupEl.className = 'map-group';
          groupEl.innerHTML = `
            <button type="button" class="map-group-head" data-group-key="${escapeHtml(group.key)}">
              <span class="map-group-dot" style="background:${group.color}"></span>
              <span class="map-group-title">${escapeHtml(group.workTitle)}</span>
              <span class="map-group-meta">${escapeHtml(typeLabel[group.ipType] || '')} · ${group.itemIds.length}</span>
            </button>
            <ul class="map-group-items"></ul>`;
          const itemsEl = groupEl.querySelector('.map-group-items');
          group.itemIds.forEach((id) => {
            const entry = itemEntries.get(id);
            const li = document.createElement('li');
            li.className = 'map-locate-item';
            li.dataset.id = id;
            li.innerHTML = `<span class="map-locate-name">${escapeHtml(entry.item.name)}</span>`;
            itemsEl.appendChild(li);
            entry.listItem = li;
          });
          listElement.appendChild(groupEl);
          groups.push(group);
        });
      }
    })
    .catch((error) => {
      element.setAttribute('aria-label', error.message);
      map.setView([35.8617, 104.1954], 4);
      showEmpty(error.message);
    });

  // 搜索：按作品名或地标名模糊匹配
  if (searchInput) {
    searchInput.addEventListener('input', () => {
      const query = searchInput.value.trim().toLowerCase();
      groups.forEach((group) => {
        const groupMatched = !query || group.workTitle.toLowerCase().includes(query);
        let visibleCount = 0;
        group.itemIds.forEach((id) => {
          const entry = itemEntries.get(id);
          const matched = groupMatched
            || entry.item.name.toLowerCase().includes(query)
            || (typeLabel[entry.item.ip_type] || '').toLowerCase().includes(query);
          entry.listItem.hidden = !matched;
          if (matched) visibleCount += 1;
        });
        group.groupEl.hidden = visibleCount === 0;
      });
    });
  }

  // 点击：作品头 → 聚焦该作品全部地标；地标项 → 聚焦单个地标
  if (listElement) {
    listElement.addEventListener('click', (event) => {
      const head = event.target.closest('.map-group-head');
      if (head) {
        const group = groups.find((candidate) => candidate.key === head.dataset.groupKey);
        if (!group) return;
        const latlngs = group.itemIds.map((id) => itemEntries.get(id)).map(({ item }) => [item.latitude, item.longitude]);
        if (latlngs.length) map.flyToBounds(L.latLngBounds(latlngs).pad(0.3), { duration: 0.8 });
        return;
      }

      const listItem = event.target.closest('.map-locate-item');
      if (!listItem) return;
      const entry = itemEntries.get(listItem.dataset.id);
      if (!entry) return;
      itemEntries.forEach(({ listItem: other }) => other && other.classList.remove('is-active'));
      listItem.classList.add('is-active');
      map.flyTo([entry.item.latitude, entry.item.longitude], Math.max(map.getZoom(), 14), { duration: 0.8 });
      map.once('moveend', () => entry.marker.openPopup());
    });
  }

  if (resetButton) {
    resetButton.addEventListener('click', resetView);
  }
})();
