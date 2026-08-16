(() => {
  const exportLinks = document.querySelectorAll('a[href*="/exports/"], a.export-link');
  exportLinks.forEach((link) => {
    link.addEventListener('click', () => {
      const original = link.textContent;
      link.textContent = '正在导出…';
      link.setAttribute('aria-busy', 'true');
      setTimeout(() => {
        link.textContent = original;
        link.removeAttribute('aria-busy');
      }, 2500);
    });
  });
})();
