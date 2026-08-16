(() => {
  const element = document.getElementById('itinerary-map');
  const dataElement = document.getElementById('itinerary-map-data');
  if (!element || !dataElement || !window.L) return;

  const escapeHtml = (value) => String(value).replace(/[&<>'"]/g, (character) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' })[character]);

  let payload;
  try {
    payload = JSON.parse(dataElement.textContent);
  } catch (error) {
    return;
  }
  const days = (payload.days || []).filter((day) => day.stops && day.stops.length);
  if (!days.length) return;

  const map = L.map(element, { scrollWheelZoom: false });
  L.tileLayer(element.dataset.tileUrl, { maxZoom: 18, attribution: '© OpenStreetMap contributors' }).addTo(map);

  const palette = ['#0b5c63', '#b4552d', '#2f6b9c', '#6b8e23', '#7f3f98', '#c05a2a', '#3b6d11'];
  const bounds = [];

  days.forEach((day, dayIndex) => {
    const color = palette[dayIndex % palette.length];
    const points = day.stops.map((stop) => {
      const latlng = [stop.lat, stop.lng];
      bounds.push(latlng);
      const label = `D${day.day_number}-${stop.order}`;
      L.circleMarker(latlng, { radius: 8, color: color, weight: 2, fillColor: '#ffffff', fillOpacity: 1 })
        .bindTooltip(label, { permanent: true, direction: 'top', offset: [0, -10] })
        .bindPopup(`<strong>${escapeHtml(stop.name)}</strong><br>${label}<br><a href="${escapeHtml(stop.detail_url)}">查看详情</a>`)
        .addTo(map);
      return latlng;
    });
    if (points.length > 1) {
      L.polyline(points, { color: color, weight: 3, opacity: 0.85 }).addTo(map);
    }
  });

  if (bounds.length) {
    map.fitBounds(L.latLngBounds(bounds).pad(0.2));
  }
})();
