/* 图片失效时的可理解占位：隐藏破图，露出卡片首字占位块。 */
(function () {
  "use strict";
  document.addEventListener(
    "error",
    function (event) {
      var target = event.target;
      if (!target || target.tagName !== "IMG") return;
      target.classList.add("is-broken");
      target.setAttribute("aria-hidden", "true");
      var media = target.closest(".card-media");
      if (media && !media.querySelector(".card-placeholder")) {
        var placeholder = document.createElement("span");
        placeholder.className = "card-placeholder";
        placeholder.setAttribute("aria-hidden", "true");
        placeholder.textContent = "图";
        media.appendChild(placeholder);
      }
    },
    true
  );
})();
