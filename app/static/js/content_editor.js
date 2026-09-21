/* 地标文字内容编辑：贡献者/管理员可见；贡献者保存后进入重新审核。 */
(function () {
  "use strict";

  var landmarkId = document.body.dataset.landmarkId;
  var section = document.getElementById("content-editor");
  if (!section) return;

  var form = document.getElementById("content-form");
  var nameInput = document.getElementById("content-name");
  var descInput = document.getElementById("content-description");
  var transitInput = document.getElementById("content-transit");
  var kindInput = document.getElementById("content-kind");
  var saveButton = document.getElementById("content-save");
  var statusEl = document.getElementById("content-status");
  var errorEl = document.getElementById("content-error");
  var busy = false;

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = text;
    return node;
  }

  function request(method, url, body) {
    var options = { method: method };
    if (body !== undefined) {
      options.headers = { "Content-Type": "application/json" };
      options.body = JSON.stringify(body);
    }
    return fetch(url, options).then(function (response) {
      return response.json().then(function (data) {
        if (!response.ok) {
          var detail = data && data.detail ? data.detail : "请求失败（" + response.status + "）";
          throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
        }
        return data;
      });
    });
  }

  function load() {
    request("GET", "/api/v1/landmarks/" + landmarkId + "/content")
      .then(function (data) {
        nameInput.value = data.name || "";
        descInput.value = data.description || "";
        transitInput.value = data.transit_text || "";
        kindInput.value = data.landmark_kind || "";
        section.style.display = "";
        if (!data.published) {
          statusEl.textContent = "当前状态：待审核（修改将再次进入审核）";
        } else if (data.is_admin) {
          statusEl.textContent = "当前状态：已上架（管理员修改即时生效）";
        }
      })
      .catch(function (error) {
        // 非贡献者/管理员：整个文字编辑区隐藏
        if (error.message.indexOf("贡献者") !== -1 || error.message.indexOf("管理员") !== -1 || error.message.indexOf("登录") !== -1) {
          section.style.display = "none";
          return;
        }
        section.style.display = "";
        errorEl.textContent = "加载失败：" + error.message;
      });
  }

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    if (busy) return;
    if (!nameInput.value.trim() || !descInput.value.trim()) {
      errorEl.textContent = "名称与简介不能为空。";
      return;
    }
    busy = true;
    saveButton.disabled = true;
    errorEl.textContent = "";
    statusEl.textContent = "正在保存……";
    request("PATCH", "/api/v1/landmarks/" + landmarkId + "/content", {
      name: nameInput.value,
      description: descInput.value,
      transit_text: transitInput.value,
      landmark_kind: kindInput.value
    }).then(function (data) {
      busy = false;
      saveButton.disabled = false;
      statusEl.textContent = "✓ " + (data.note || "已保存");
    }).catch(function (error) {
      busy = false;
      saveButton.disabled = false;
      statusEl.textContent = "";
      errorEl.textContent = error.message;
    });
  });

  load();
})();
