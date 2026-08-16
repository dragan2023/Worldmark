(() => {
  const form = document.querySelector('[data-cascade-filter]');
  if (!form) return;
  const country = form.querySelector('[data-country-select]');
  const province = form.querySelector('[data-province-select]');
  const city = form.querySelector('[data-city-select]');
  if (!country || !province || !city) return;

  function applyCascade() {
    const selectedCountry = country.value;
    for (const option of province.options) {
      option.hidden = Boolean(option.value) && Boolean(selectedCountry) && option.dataset.country !== selectedCountry;
    }
    if (province.selectedOptions[0] && province.selectedOptions[0].hidden) province.value = '';

    const selectedProvince = province.value;
    for (const option of city.options) {
      if (!option.value) { option.hidden = false; continue; }
      const countryOk = !selectedCountry || option.dataset.country === selectedCountry;
      const provinceOk = !selectedProvince || option.dataset.province === selectedProvince;
      option.hidden = !(countryOk && provinceOk);
    }
    if (city.selectedOptions[0] && city.selectedOptions[0].hidden) city.value = '';
  }

  country.addEventListener('change', () => { province.value = ''; city.value = ''; applyCascade(); });
  province.addEventListener('change', () => { city.value = ''; applyCascade(); });
  applyCascade();

  document.querySelectorAll('.module-tabs a').forEach((link) => {
    link.addEventListener('click', () => {
      const url = new URL(link.href);
      const current = new URL(window.location.href);
      ['country', 'province', 'city'].forEach((key) => {
        if (current.searchParams.has(key)) url.searchParams.set(key, current.searchParams.get(key));
      });
      link.href = url.toString();
    });
  });
})();
