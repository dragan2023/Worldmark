(() => {
  const element = document.getElementById('landmark-map');
  if (!element) return;
  const statusElement = document.getElementById('map-status');
  const setStatus = (text) => { if (statusElement) statusElement.textContent = text || ''; };
  if (!window.L) { setStatus('地图组件未能加载，列表与筛选仍可使用。'); return; }

  const escapeHtml = (value) => String(value).replace(/[&<>'"]/g, (character) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' })[character]);

  const colorByType = { literature: '#0b5c63', game: '#b4552d', screen: '#2f6b9c' };
  const typeLabel = { literature: '文学', game: '游戏', screen: '影视' };

  const searchInput = document.getElementById('map-locate-search');
  const resetButton = document.getElementById('map-locate-reset');
  const listElement = document.getElementById('map-locate-list');
  const countElement = document.getElementById('map-locate-count');

  const map = L.map(element, { scrollWheelZoom: true, wheelPxPerZoomLevel: 120 });
  const tiles = L.tileLayer(element.dataset.tileUrl, { maxZoom: 18, attribution: '© OpenStreetMap contributors' });
  tiles.on('tileerror', () => setStatus('地图瓦片加载失败，可能是网络或瓦片服务不可达；点位列表仍可正常使用。'));
  tiles.addTo(map);

  const pinIcon = (color) => L.divIcon({
    className: 'map-pin',
    html: `<svg viewBox="0 0 24 24" width="30" height="30" aria-hidden="true"><path d="M12 2C7.58 2 4 5.58 4 10c0 5.25 8 12 8 12s8-6.75 8-12c0-4.42-3.58-8-8-8z" fill="${color}" stroke="#ffffff" stroke-width="1.5"/><circle cx="12" cy="10" r="3" fill="#ffffff"/></svg>`,
    iconSize: [30, 30],
    iconAnchor: [15, 30],
    popupAnchor: [0, -28],
  });

  let markerGroup = null;
  let truncationNotice = '';
  const itemEntries = new Map(); // id -> { marker, item, listItem }
  const groups = []; // { key, workTitle, ipType, color, itemIds, groupEl }

  const CHINA_CENTER = [35.8617, 104.1954];

  const showEmpty = (message) => {
    if (!listElement) return;
    const item = document.createElement('li');
    item.className = 'map-locate-empty';
    item.textContent = message;
    listElement.appendChild(item);
  };

  const allLatLngs = () => [...itemEntries.values()].map(({ item }) => [item.latitude, item.longitude]);

  const fitAll = () => {
    const latlngs = allLatLngs();
    if (latlngs.length === 1) {
      map.setView(latlngs[0], 12); // 单点：直接定位，避免 fitBounds 出现空白级别
      return;
    }
    if (latlngs.length) map.fitBounds(L.latLngBounds(latlngs).pad(0.16));
    else map.setView(CHINA_CENTER, 4);
  };

  const updateCount = (visibleMarkers, visibleGroups) => {
    if (!countElement) return;
    const total = itemEntries.size;
    countElement.textContent = visibleMarkers === total
      ? `共 ${total} 个地标点`
      : `筛选出 ${visibleMarkers} / ${total} 个地标点（${visibleGroups} 个作品）`;
  };

  /** 过滤：同时更新列表可见性、地图标记与数量；query 为空即全部显示。 */
  const applyFilter = () => {
    const query = (searchInput ? searchInput.value : '').trim().toLowerCase();
    let visibleMarkers = 0;
    let visibleGroups = 0;
    groups.forEach((group) => {
      const groupMatched = !query || group.workTitle.toLowerCase().includes(query);
      let visibleInGroup = 0;
      group.itemIds.forEach((id) => {
        const entry = itemEntries.get(id);
        if (!entry) return;
        const matched = groupMatched
          || entry.item.name.toLowerCase().includes(query)
          || (typeLabel[entry.item.ip_type] || '').toLowerCase().includes(query);
        if (entry.listItem) entry.listItem.hidden = !matched;
        if (entry.marker) {
          if (matched) { markerGroup.addLayer(entry.marker); visibleInGroup += 1; }
          else markerGroup.removeLayer(entry.marker);
        }
      });
      if (group.groupEl) group.groupEl.hidden = visibleInGroup === 0;
      visibleMarkers += visibleInGroup;
      if (visibleInGroup) visibleGroups += 1;
    });
    updateCount(visibleMarkers, visibleGroups);
    if (!visibleMarkers) setStatus(query ? `没有匹配「${searchInput.value.trim()}」的地标，试试其他关键词或重置。` : '当前筛选下暂无地标点位。');
    else setStatus(truncationNotice);
  };

  /** 重置：清空搜索 + 恢复全部标记 + 回到全局视野。 */
  const resetView = () => {
    if (searchInput) searchInput.value = '';
    applyFilter();
    fitAll();
  };

  fetch(element.dataset.apiUrl, { credentials: 'same-origin' })
    .then((response) => response.ok ? response.json() : Promise.reject(new Error('地图数据暂不可用，请稍后重试。')))
    .then(({ items, truncated, limit }) => {
      if (truncated) {
        truncationNotice = `点位较多，只显示前 ${limit || items.length} 个；请用筛选条件缩小范围。`;
        setStatus(truncationNotice);
      }
      if (!items.length) {
        map.setView(CHINA_CENTER, 4);
        showEmpty('当前筛选下暂无地标点位。');
        setStatus('当前筛选下暂无地标点位。');
        updateCount(0, 0);
        return;
      }

      markerGroup = L.featureGroup();
      const byKey = new Map();

      items.forEach((item) => {
        const color = colorByType[item.ip_type] || '#0b5c63';
        const marker = L.marker([item.latitude, item.longitude], { icon: pinIcon(color), title: item.name })
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
      fitAll();

      if (listElement) {
        byKey.forEach((group) => {
          const groupEl = document.createElement('li');
          groupEl.className = 'map-group';
          const head = document.createElement('button');
          head.type = 'button';
          head.className = 'map-group-head';
          head.dataset.groupKey = group.key;
          head.setAttribute('aria-expanded', 'true');
          head.innerHTML = `
            <span class="map-group-dot" style="background:${group.color}" aria-hidden="true"></span>
            <span class="map-group-title">${escapeHtml(group.workTitle)}</span>
            <span class="map-group-meta">${escapeHtml(typeLabel[group.ipType] || '')} · ${group.itemIds.length}</span>`;
          const itemsEl = document.createElement('ul');
          itemsEl.className = 'map-group-items';
          group.itemIds.forEach((id) => {
            const entry = itemEntries.get(id);
            const li = document.createElement('li');
            li.className = 'map-locate-item';
            li.dataset.id = id;
            const button = document.createElement('button');
            button.type = 'button';
            button.className = 'map-locate-button';
            button.textContent = entry.item.name;
            li.appendChild(button);
            itemsEl.appendChild(li);
            entry.listItem = li;
          });
          groupEl.append(head, itemsEl);
          listElement.appendChild(groupEl);
          group.groupEl = groupEl; // 修复：搜索时需要整组隐藏
          groups.push(group);
        });
        updateCount(itemEntries.size, groups.length);
      }
    })
    .catch((error) => {
      setStatus(error.message);
      map.setView(CHINA_CENTER, 4);
      showEmpty(error.message);
    });

  if (searchInput) {
    searchInput.addEventListener('input', applyFilter);
    searchInput.addEventListener('keydown', (event) => {
      if (event.key === 'Escape') { event.preventDefault(); resetView(); }
    });
  }

  if (listElement) {
    listElement.addEventListener('click', (event) => {
      const head = event.target.closest('.map-group-head');
      if (head) {
        const group = groups.find((candidate) => candidate.key === head.dataset.groupKey);
        if (!group) return;
        const latlngs = group.itemIds.map((id) => itemEntries.get(id)).filter(Boolean).map(({ item }) => [item.latitude, item.longitude]);
        if (latlngs.length === 1) map.flyTo(latlngs[0], 12, { duration: 0.6 });
        else if (latlngs.length) map.flyToBounds(L.latLngBounds(latlngs).pad(0.3), { duration: 0.8 });
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

  if (resetButton) resetButton.addEventListener('click', resetView);
})();
