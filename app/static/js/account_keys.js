/* 个人密钥页：拉取密钥目录、保存/验证/删除用户自配密钥。 */
(function () {
  "use strict";

  var list = document.getElementById("keys-list");
  var message = document.getElementById("keys-message");

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function fail(text) {
    message.textContent = text;
  }

  function load() {
    message.textContent = "";
    fetch("/api/v1/me/api-keys").then(function (response) {
      if (response.status === 401) {
        window.location.href = "/login?next=/account/api-keys";
        return null;
      }
      return response.json();
    }).then(function (data) {
      if (!data) return;
      list.innerHTML = "";
      data.items.forEach(function (item) { list.appendChild(renderCard(item)); });
    }).catch(function () { fail("加载失败，请刷新重试。"); });
  }

  function renderCard(item) {
    var card = el("div", "key-card");
    var head = el("div", "key-card-head");
    head.appendChild(el("h2", "key-label", item.label));
    var badge = el("span", "key-badge " + (item.configured ? "configured" : "missing"),
      item.configured ? "已配置 " + (item.key_hint || "") : "未配置");
    head.appendChild(badge);
    card.appendChild(head);

    card.appendChild(el("p", "key-hint", item.hint));
    var apply = el("a", "key-apply-link", "前往申请密钥 ↗");
    apply.href = item.apply_url;
    apply.target = "_blank";
    apply.rel = "noopener";
    card.appendChild(apply);

    var input = el("input", "auth-input key-input");
    input.type = "password";
    input.placeholder = item.configured ? "输入新密钥以覆盖" : "粘贴你的密钥";
    input.autocomplete = "off";
    card.appendChild(input);

    var actions = el("div", "key-actions");
    var verifyBox = el("label", "key-verify-box");
    var verify = el("input");
    verify.type = "checkbox";
    verify.checked = true;
    verifyBox.appendChild(verify);
    verifyBox.appendChild(document.createTextNode("保存前验证连通性"));
    actions.appendChild(verifyBox);

    var save = el("button", "primary-button key-save", "保存");
    save.type = "button";
    save.addEventListener("click", function () { saveKey(item, input, verify.checked, save); });
    actions.appendChild(save);

    if (item.configured) {
      var test = el("button", "secondary-button key-test", "测试");
      test.type = "button";
      test.addEventListener("click", function () { testKey(item, test); });
      actions.appendChild(test);

      var remove = el("button", "secondary-button key-delete", "删除");
      remove.type = "button";
      remove.addEventListener("click", function () { deleteKey(item, remove); });
      actions.appendChild(remove);
    }
    card.appendChild(actions);

    var note = el("p", "key-note", "");
    card.appendChild(note);
    return card;
  }

  function saveKey(item, input, doVerify, button) {
    var value = input.value.trim();
    if (!value) { fail("请先输入密钥内容。"); return; }
    button.disabled = true;
    fetch("/api/v1/me/api-keys/" + item.provider, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ value: value, verify: doVerify })
    }).then(function (response) {
      return response.json().then(function (body) { return { ok: response.ok, body: body }; });
    }).then(function (result) {
      button.disabled = false;
      if (result.ok) { input.value = ""; load(); return; }
      fail(result.body.detail || "保存失败。");
    }).catch(function () { button.disabled = false; fail("网络错误，保存失败。"); });
  }

  function testKey(item, button) {
    button.disabled = true;
    fetch("/api/v1/me/api-keys/" + item.provider + "/verify", { method: "POST" })
      .then(function (r) { return r.json(); })
      .then(function (body) {
        button.disabled = false;
        fail(body.ok ? "✓ " + (body.message || "验证通过") : "✗ " + (body.message || "验证失败"));
        if (body.ok) load();
      }).catch(function () { button.disabled = false; fail("网络错误。"); });
  }

  function deleteKey(item, button) {
    if (!window.confirm("确定删除已保存的 " + item.label + " 密钥？")) return;
    button.disabled = true;
    fetch("/api/v1/me/api-keys/" + item.provider, { method: "DELETE" })
      .then(function () { load(); })
      .catch(function () { button.disabled = false; fail("删除失败。"); });
  }

  load();
})();
