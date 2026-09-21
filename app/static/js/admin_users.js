/* 用户管理页：列表 / 搜索 / 角色调整 / 封禁与解封。 */
(function () {
  "use strict";

  var ROLE_LABELS = { admin: "管理员", level1: "一级用户", level2: "二级用户" };
  var list = document.getElementById("users-list");
  var message = document.getElementById("users-message");
  var searchBox = document.getElementById("users-search");
  var searchTimer = null;

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function fail(text) { message.textContent = text; }

  function load() {
    var q = (searchBox.value || "").trim();
    var url = "/api/v1/admin/users?limit=200" + (q ? "&q=" + encodeURIComponent(q) : "");
    fetch(url).then(function (response) {
      if (response.status === 401 || response.status === 403) {
        window.location.href = "/login?next=/admin/users";
        return null;
      }
      return response.json();
    }).then(function (data) {
      if (!data) return;
      list.innerHTML = "";
      if (!data.items.length) {
        list.appendChild(el("p", "keys-loading", "没有匹配的用户。"));
        return;
      }
      data.items.forEach(function (user) { list.appendChild(renderRow(user)); });
    }).catch(function () { fail("加载失败，请刷新重试。"); });
  }

  function renderRow(user) {
    var card = el("div", "key-card user-card" + (user.status === "banned" ? " banned" : ""));
    var head = el("div", "key-card-head");
    var nameBox = el("div");
    nameBox.appendChild(el("strong", null, user.username));
    nameBox.appendChild(el("div", "key-hint", user.email + " ｜ 注册于 " + (user.created_at || "").slice(0, 10) +
      (user.last_login_at ? " ｜ 最近登录 " + user.last_login_at.slice(0, 16).replace("T", " ") : " ｜ 从未登录")));
    head.appendChild(nameBox);
    head.appendChild(el("span", "key-badge " + (user.status === "active" ? "configured" : "missing"),
      user.status === "active" ? "正常" : "已封禁"));
    card.appendChild(head);

    var actions = el("div", "key-actions");

    var roleSelect = el("select", "auth-input role-select");
    ["admin", "level1", "level2"].forEach(function (role) {
      var option = el("option", null, ROLE_LABELS[role]);
      option.value = role;
      if (role === user.role) option.selected = true;
      roleSelect.appendChild(option);
    });
    roleSelect.addEventListener("change", function () {
      patch(user, { role: roleSelect.value }, function (ok, body) {
        if (ok) { load(); } else { fail(body.detail || "调整失败。"); load(); }
      });
    });
    actions.appendChild(roleSelect);

    var tierBadge = el("span", "key-hint", "会员档：" + (user.tier || "-"));
    actions.appendChild(tierBadge);

    if (user.status === "active") {
      var ban = el("button", "secondary-button", "封禁");
      ban.type = "button";
      ban.addEventListener("click", function () {
        if (!window.confirm("确定封禁 " + user.email + "？其已签发的登录将立即失效。")) return;
        patch(user, { status: "banned" }, function (ok, body) {
          if (ok) { load(); } else { fail(body.detail || "封禁失败。"); }
        });
      });
      actions.appendChild(ban);
    } else {
      var unban = el("button", "primary-button", "解封");
      unban.type = "button";
      unban.addEventListener("click", function () {
        patch(user, { status: "active" }, function (ok, body) {
          if (ok) { load(); } else { fail(body.detail || "解封失败。"); }
        });
      });
      actions.appendChild(unban);
    }
    card.appendChild(actions);
    return card;
  }

  function patch(user, payload, done) {
    fetch("/api/v1/admin/users/" + user.id, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    }).then(function (response) {
      return response.json().then(function (body) { done(response.ok, body); });
    }).catch(function () { fail("网络错误。"); });
  }

  searchBox.addEventListener("input", function () {
    if (searchTimer) clearTimeout(searchTimer);
    searchTimer = setTimeout(load, 300);
  });

  load();
})();
