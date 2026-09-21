/* 管理后台：用户管理 + 地标审核（仅管理员页面）。 */
(function () {
  "use strict";

  var ROLE_LABELS = { admin: "管理员", level1: "一级用户", level2: "二级用户" };
  var STATUS_LABELS = { candidate: "待审核", verified: "已核验", rejected: "已驳回" };
  var me = null;

  var usersList = document.getElementById("users-list");
  var usersCount = document.getElementById("users-count");
  var usersMessage = document.getElementById("users-message");
  var usersSearch = document.getElementById("users-search");

  var lmList = document.getElementById("landmarks-list");
  var lmCount = document.getElementById("lm-count");
  var lmMessage = document.getElementById("landmarks-message");
  var lmSearch = document.getElementById("lm-search");
  var lmStatus = "pending";

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function fail(box, text) { box.textContent = text; }

  function fetchJson(url, options) {
    return fetch(url, options).then(function (response) {
      if (response.status === 401) {
        window.location.href = "/login?next=/admin";
        return null;
      }
      return response.json().then(function (body) { return { ok: response.ok, body: body }; });
    });
  }

  /* ---------------- Tab 切换 ---------------- */
  var tabs = document.querySelectorAll(".admin-tab[data-tab]");
  tabs.forEach(function (tab) {
    tab.addEventListener("click", function () {
      tabs.forEach(function (t) { t.classList.remove("active"); });
      tab.classList.add("active");
      document.querySelectorAll(".admin-panel").forEach(function (panel) { panel.classList.remove("active"); });
      document.getElementById("tab-" + tab.dataset.tab).classList.add("active");
    });
  });

  /* ---------------- 用户管理 ---------------- */
  var usersTimer = null;

  function loadUsers() {
    var q = (usersSearch.value || "").trim();
    fetchJson("/api/v1/admin/users?limit=200" + (q ? "&q=" + encodeURIComponent(q) : ""))
      .then(function (result) {
        if (!result) return;
        usersList.innerHTML = "";
        usersCount.textContent = "共 " + result.body.total + " 个账号";
        if (!result.body.items.length) {
          usersList.appendChild(el("p", "keys-loading", "没有匹配的用户。"));
          return;
        }
        result.body.items.forEach(function (user) { usersList.appendChild(renderUser(user)); });
      })
      .catch(function () { fail(usersMessage, "加载失败，请刷新重试。"); });
  }

  function renderUser(user) {
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
      patchUser(user, { role: roleSelect.value }, function (ok, body) {
        if (!ok) fail(usersMessage, body.detail || "调整失败。");
        loadUsers();
      });
    });
    actions.appendChild(roleSelect);

    actions.appendChild(el("span", "key-hint", "会员档：" + (user.tier || "-")));

    if (user.status === "active") {
      var ban = el("button", "secondary-button", "封禁");
      ban.type = "button";
      ban.addEventListener("click", function () {
        if (!window.confirm("确定封禁 " + user.username + "？其已签发的登录将立即失效。")) return;
        patchUser(user, { status: "banned" }, function (ok, body) {
          if (!ok) fail(usersMessage, body.detail || "封禁失败。");
          loadUsers();
        });
      });
      actions.appendChild(ban);
    } else {
      var unban = el("button", "primary-button", "解封");
      unban.type = "button";
      unban.addEventListener("click", function () {
        patchUser(user, { status: "active" }, function (ok, body) {
          if (!ok) fail(usersMessage, body.detail || "解封失败。");
          loadUsers();
        });
      });
      actions.appendChild(unban);
    }
    card.appendChild(actions);
    return card;
  }

  function patchUser(user, payload, done) {
    fetchJson("/api/v1/admin/users/" + user.id, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    }).then(function (result) { if (result) done(result.ok, result.body); })
      .catch(function () { fail(usersMessage, "网络错误。"); });
  }

  usersSearch.addEventListener("input", function () {
    if (usersTimer) clearTimeout(usersTimer);
    usersTimer = setTimeout(loadUsers, 300);
  });

  /* ---------------- 地标审核 ---------------- */
  var lmTimer = null;

  function loadLandmarks() {
    var q = (lmSearch.value || "").trim();
    fetchJson("/api/v1/admin/landmarks?status=" + lmStatus + "&limit=200" + (q ? "&q=" + encodeURIComponent(q) : ""))
      .then(function (result) {
        if (!result) return;
        lmList.innerHTML = "";
        lmCount.textContent = "共 " + result.body.total + " 条";
        if (!result.body.items.length) {
          lmList.appendChild(el("p", "keys-loading", "该状态下暂无地标。"));
          return;
        }
        result.body.items.forEach(function (item) { lmList.appendChild(renderLandmark(item)); });
      })
      .catch(function () { fail(lmMessage, "加载失败，请刷新重试。"); });
  }

  function renderLandmark(item) {
    var card = el("div", "key-card lm-card" + (item.deleted ? " banned" : ""));
    var head = el("div", "key-card-head");
    var nameBox = el("div");
    var title = el("strong", null, item.name + " ");
    nameBox.appendChild(title);
    nameBox.appendChild(el("span", "key-hint",
      "《" + item.work_title + "》· " + item.ip_type + " · " + (item.region || "未知地区") +
      " · 来源 " + item.source_count + " 条" +
      (item.contributor ? " · 贡献者 " + item.contributor : "")));
    head.appendChild(nameBox);

    var badges = el("div", "lm-badges");
    badges.appendChild(el("span", "key-badge " + (item.verification_status === "verified" ? "configured" : "missing"),
      STATUS_LABELS[item.verification_status] || item.verification_status));
    if (item.published) badges.appendChild(el("span", "key-badge configured", "已发布"));
    if (item.deleted) badges.appendChild(el("span", "key-badge missing", "已删除"));
    head.appendChild(badges);
    card.appendChild(head);

    var actions = el("div", "key-actions");

    var detail = el("button", "secondary-button", "详情");
    detail.type = "button";
    detail.addEventListener("click", function () { showDetail(item); });
    actions.appendChild(detail);

    if (item.verification_status === "candidate" && !item.deleted) {
      var approve = el("button", "primary-button", "通过");
      approve.type = "button";
      approve.addEventListener("click", function () {
        var reason = window.prompt("核验说明（将记录为审核意见）：", "内容核验通过");
        if (reason === null) return;
        reviewLandmark(item, "verified", reason || "内容核验通过", approve);
      });
      actions.appendChild(approve);

      var reject = el("button", "secondary-button", "驳回");
      reject.type = "button";
      reject.addEventListener("click", function () {
        var reason = window.prompt("驳回理由（必填）：", "");
        if (reason === null) return;
        if (!reason.trim()) { fail(lmMessage, "驳回必须填写理由。"); return; }
        reviewLandmark(item, "rejected", reason.trim(), reject);
      });
      actions.appendChild(reject);
    }

    if (item.verification_status === "verified" && !item.published && !item.deleted) {
      var publish = el("button", "primary-button", "发布上架");
      publish.type = "button";
      publish.addEventListener("click", function () {
        act("/api/v1/admin/landmarks/" + item.id + "/publish", { method: "POST" }, publish, function () { loadLandmarks(); });
      });
      actions.appendChild(publish);
    }

    if (item.published && !item.deleted) {
      var unpublish = el("button", "secondary-button", "下架");
      unpublish.type = "button";
      unpublish.addEventListener("click", function () {
        if (!window.confirm("确定下架「" + item.name + "」？将从目录与地图中隐藏。")) return;
        act("/api/v1/admin/landmarks/" + item.id + "/unpublish", { method: "POST" }, unpublish, function () { loadLandmarks(); });
      });
      actions.appendChild(unpublish);
    }

    if (!item.deleted) {
      var edit = el("button", "secondary-button", "编辑");
      edit.type = "button";
      edit.addEventListener("click", function () { toggleEdit(item, card); });
      actions.appendChild(edit);

      var del = el("button", "secondary-button lm-danger", "删除");
      del.type = "button";
      del.addEventListener("click", function () {
        if (!window.confirm("确定删除「" + item.name + "」？将进入回收站，可恢复。")) return;
        act("/api/v1/admin/landmarks/" + item.id, { method: "DELETE" }, del, function () { loadLandmarks(); });
      });
      actions.appendChild(del);
    } else {
      var restore = el("button", "primary-button", "恢复");
      restore.type = "button";
      restore.addEventListener("click", function () {
        act("/api/v1/admin/landmarks/" + item.id + "/restore", { method: "POST" }, restore, function () { loadLandmarks(); });
      });
      actions.appendChild(restore);
    }
    card.appendChild(actions);
    return card;
  }

  function toggleEdit(item, card) {
    var existing = card.querySelector(".lm-edit-form");
    if (existing) { existing.remove(); return; }
    var form = el("div", "lm-edit-form");
    var nameLabel = el("label", "auth-label", "地标名称");
    var nameInput = el("input", "auth-input");
    nameInput.value = item.name;
    var descLabel = el("label", "auth-label", "简介");
    var descInput = el("textarea", "auth-input lm-textarea");
    descInput.rows = 4;
    fetchJson("/api/v1/admin/landmarks/" + item.id)
      .then(function (result) {
        if (result && result.ok) descInput.value = result.body.description || "";
      });
    var transitLabel = el("label", "auth-label", "交通信息");
    var transitInput = el("input", "auth-input");
    fetchJson("/api/v1/admin/landmarks/" + item.id)
      .then(function (result) {
        if (result && result.ok) transitInput.value = result.body.transit_text || "";
      });

    var save = el("button", "primary-button", "保存修改");
    save.type = "button";
    save.addEventListener("click", function () {
      act("/api/v1/admin/landmarks/" + item.id, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: nameInput.value,
          description: descInput.value,
          transit_text: transitInput.value
        })
      }, save, function () {
        form.remove();
        loadLandmarks();
      });
    });
    var cancel = el("button", "secondary-button", "取消");
    cancel.type = "button";
    cancel.addEventListener("click", function () { form.remove(); });

    form.appendChild(nameLabel); form.appendChild(nameInput);
    form.appendChild(descLabel); form.appendChild(descInput);
    form.appendChild(transitLabel); form.appendChild(transitInput);
    var row = el("div", "key-actions");
    row.appendChild(save); row.appendChild(cancel);
    form.appendChild(row);
    card.appendChild(form);
  }

  function showDetail(item) {
    var overlay = document.createElement("div");
    overlay.className = "lm-modal-overlay";
    var modal = el("div", "lm-modal");
    modal.appendChild(el("h2", "lm-modal-title", "审核详情：" + item.name));
    var content = el("div", "lm-modal-body", "正在加载…");
    modal.appendChild(content);
    var closeRow = el("div", "key-actions");
    var close = el("button", "primary-button", "关闭");
    close.type = "button";
    close.addEventListener("click", function () { overlay.remove(); });
    closeRow.appendChild(close);
    modal.appendChild(closeRow);
    overlay.appendChild(modal);
    overlay.addEventListener("click", function (event) {
      if (event.target === overlay) overlay.remove();
    });
    document.body.appendChild(overlay);

    fetchJson("/api/v1/admin/landmarks/" + item.id).then(function (result) {
      if (!result) { overlay.remove(); return; }
      if (!result.ok) { content.textContent = result.body.detail || "加载失败。"; return; }
      renderDetail(content, result.body);
    }).catch(function () { content.textContent = "网络错误。"; });
  }

  function renderDetail(box, data) {
    box.innerHTML = "";

    var meta = el("div", "lm-meta");
    meta.appendChild(el("p", null, "作品：《" + (data.work_title || "-") + "》" + (data.work_aliases ? "（别名：" + data.work_aliases + "）" : "")));
    meta.appendChild(el("p", null, "IP 类型：" + (data.ip_type || "-") + " ｜ 地区：" + (data.region || "未知")));
    meta.appendChild(el("p", null, "地址：" + (data.address || "未提供")));
    meta.appendChild(el("p", null, "状态：" + (STATUS_LABELS[data.verification_status] || data.verification_status) +
      (data.published_at ? " ｜ 发布于 " + data.published_at.slice(0, 10) : "") +
      (data.deleted_at ? " ｜ 已删除" : "") +
      (data.contributor ? " ｜ 贡献者：" + data.contributor : "")));
    box.appendChild(meta);

    box.appendChild(el("h3", "lm-section-title", "简介（检查有无违规内容）"));
    box.appendChild(el("p", "lm-text", data.description || "（无）"));
    box.appendChild(el("h3", "lm-section-title", "交通信息"));
    box.appendChild(el("p", "lm-text", data.transit_text || "（无）"));

    box.appendChild(el("h3", "lm-section-title", "来源（" + data.sources.length + " 条）"));
    if (data.sources.length) {
      var srcList = el("ul", "lm-source-list");
      data.sources.forEach(function (source) {
        var li = el("li");
        var link = el("a", null, source.title || source.url);
        link.href = source.url;
        link.target = "_blank";
        link.rel = "noopener";
        li.appendChild(link);
        li.appendChild(document.createTextNode(
          " — " + (source.publisher || "") + "（" + (source.source_type || "") +
          (source.accessed_at ? "，访问于 " + source.accessed_at.slice(0, 10) : "") + "）"
        ));
        srcList.appendChild(li);
      });
      box.appendChild(srcList);
    } else {
      box.appendChild(el("p", "key-hint", "无来源记录。"));
    }

    box.appendChild(el("h3", "lm-section-title", "图片（" + data.photos.length + " 张：正式图 / 用户上传 / AI 找图）"));
    if (data.photos.length) {
      var grid = el("div", "lm-photos");
      data.photos.forEach(function (photo) {
        var cell = el("figure", "lm-photo");
        if (photo.url) {
          var img = el("img");
          img.src = photo.url;
          img.alt = photo.alt || "";
          img.loading = "lazy";
          cell.appendChild(img);
        }
        cell.appendChild(el("span", "key-badge " + (photo.kind === "published" ? "configured" : "missing"), photo.kind_label || photo.kind));
        cell.appendChild(el("figcaption", "lm-photo-caption",
          (photo.caption ? photo.caption : "") +
          (photo.license ? " ｜ 授权：" + photo.license : "") +
          (photo.credit ? " ｜ 署名：" + photo.credit : "")));
        if (photo.source_url) {
          var photoLink = el("a", "key-hint", "图片来源 ↗");
          photoLink.href = photo.source_url;
          photoLink.target = "_blank";
          photoLink.rel = "noopener";
          cell.appendChild(photoLink);
        }
        grid.appendChild(cell);
      });
      box.appendChild(grid);
    } else {
      box.appendChild(el("p", "key-hint", "该地标暂无任何图片。"));
    }
  }

  function reviewLandmark(item, decision, reason, button) {
    act("/api/v1/admin/landmarks/" + item.id + "/review", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ decision: decision.toLowerCase(), reason: reason, reviewer_name: (me && me.username) || "admin" })
    }, button, function () { loadLandmarks(); });
  }

  function act(url, options, button, done) {
    button.disabled = true;
    fetchJson(url, options)
      .then(function (result) {
        button.disabled = false;
        if (!result) return;
        if (!result.ok) { fail(lmMessage, result.body.detail || "操作失败。"); return; }
        fail(lmMessage, "✓ 操作成功");
        done();
      })
      .catch(function () { button.disabled = false; fail(lmMessage, "网络错误。"); });
  }

  document.querySelectorAll(".lm-filter").forEach(function (btn) {
    btn.addEventListener("click", function () {
      document.querySelectorAll(".lm-filter").forEach(function (b) { b.classList.remove("active"); });
      btn.classList.add("active");
      lmStatus = btn.dataset.status;
      loadLandmarks();
    });
  });

  lmSearch.addEventListener("input", function () {
    if (lmTimer) clearTimeout(lmTimer);
    lmTimer = setTimeout(loadLandmarks, 300);
  });

  /* ---------------- 启动 ---------------- */
  fetchJson("/api/v1/auth/me").then(function (result) {
    if (result && result.body.authenticated) {
      me = result.body;
      if (me.role !== "admin") { window.location.href = "/"; return; }
    } else {
      window.location.href = "/login?next=/admin";
      return;
    }
    loadUsers();
    loadLandmarks();
  });
})();
