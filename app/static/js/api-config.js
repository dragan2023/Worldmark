/* API 配置页交互：加载状态快照、保存密钥到本机 .env、连通性验证 */
(function () {
  "use strict";

  var listEl = document.getElementById("client-list");
  var bannerEl = document.getElementById("env-banner");
  var REQUIREMENT_LABELS = { required: "必需", recommended: "建议配置", optional: "可选" };
  var STATUS_LABELS = { configured: "已配置", missing: "未配置" };

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = text;
    return node;
  }

  function request(method, url, body) {
    return fetch(url, {
      method: method,
      headers: body ? { "Content-Type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    }).then(function (response) {
      return response.json().then(function (data) {
        if (!response.ok) {
          var detail = data && data.detail ? data.detail : "请求失败（" + response.status + "）";
          throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
        }
        return data;
      });
    });
  }

  function renderBanner(config) {
    if (!config.can_edit) {
      bannerEl.textContent = "当前为生产环境（APP_ENV=production）：网页写入已禁用，请通过系统环境变量配置密钥。";
      bannerEl.classList.remove("hidden");
    }
  }

  function render(listEl, config) {
    listEl.textContent = "";
    config.clients.forEach(function (spec) {
      listEl.appendChild(renderClient(spec, config));
    });
  }

  function renderClient(spec, config) {
    var card = el("section", "config-card" + (spec.status === "configured" ? " is-configured" : " is-missing"));
    card.dataset.clientId = spec.id;

    var head = el("div", "config-card-head");
    var titleBox = el("div", "config-card-title");
    titleBox.appendChild(el("h2", null, spec.name));
    titleBox.appendChild(el("span", "config-vendor", spec.vendor));
    head.appendChild(titleBox);
    var badges = el("div", "config-badges");
    badges.appendChild(el("span", "badge status-" + spec.status, STATUS_LABELS[spec.status] || spec.status));
    badges.appendChild(el("span", "badge tag-requirement", REQUIREMENT_LABELS[spec.requirement] || spec.requirement));
    head.appendChild(badges);
    card.appendChild(head);

    card.appendChild(el("p", "config-purpose", spec.purpose));

    if (spec.features && spec.features.length) {
      var chips = el("div", "config-chips");
      spec.features.forEach(function (feature) {
        chips.appendChild(el("span", "chip", feature));
      });
      card.appendChild(chips);
    }

    var fieldsBox = el("div", "config-fields");
    spec.fields.forEach(function (field) {
      fieldsBox.appendChild(renderField(field, spec));
    });
    card.appendChild(fieldsBox);

    if (spec.note) card.appendChild(el("p", "config-note", "💡 " + spec.note));

    var actions = el("div", "config-actions");
    if (config.can_edit) {
      var saveBtn = el("button", "primary-button", "保存密钥");
      saveBtn.type = "button";
      saveBtn.addEventListener("click", function () { saveCard(card); });
      actions.appendChild(saveBtn);
    }
    var verifyBtn = el("button", "ghost-button", "测试连通");
    verifyBtn.type = "button";
    verifyBtn.addEventListener("click", function () { verifyCard(card, verifyBtn); });
    actions.appendChild(verifyBtn);

    if (spec.apply_url) {
      var applyLink = el("a", "apply-link", "申请密钥 ↗");
      applyLink.href = spec.apply_url;
      applyLink.target = "_blank";
      applyLink.rel = "noopener";
      actions.appendChild(applyLink);
    }
    if (spec.docs_url) {
      var docsLink = el("a", "apply-link secondary", "使用文档 ↗");
      docsLink.href = spec.docs_url;
      docsLink.target = "_blank";
      docsLink.rel = "noopener";
      actions.appendChild(docsLink);
    }
    card.appendChild(actions);
    card.appendChild(el("p", "verify-result", ""));
    return card;
  }

  function renderField(field, spec) {
    var row = el("div", "config-field");
    var head = el("div", "config-field-head");
    head.appendChild(el("label", null, field.label));
    head.appendChild(el("code", "config-env", field.env));
    row.appendChild(head);

    var input = document.createElement("input");
    input.type = field.secret ? "password" : "text";
    input.dataset.env = field.env;
    input.autocomplete = "off";
    input.spellcheck = false;
    input.placeholder = field.configured
      ? "已配置（" + field.masked + "），输入新值可覆盖"
      : field.placeholder || "请输入";
    row.appendChild(input);

    if (field.configured) {
      var clearBtn = el("button", "link-button", "清除");
      clearBtn.type = "button";
      clearBtn.addEventListener("click", function () {
        if (!window.confirm("确定清除 " + field.env + " 的已保存值？")) return;
        var payload = {};
        payload[field.env] = "";
        request("PUT", "/api/v1/api-config", { values: payload })
          .then(function () { loadConfig(); })
          .catch(function (error) { window.alert(error.message); });
      });
      head.appendChild(clearBtn);
    }
    if (field.hint) row.appendChild(el("p", "config-hint", field.hint));
    return row;
  }

  function saveCard(card) {
    var values = {};
    card.querySelectorAll("input[data-env]").forEach(function (input) {
      var value = input.value.trim();
      if (value) values[input.dataset.env] = value;
    });
    if (!Object.keys(values).length) {
      window.alert("没有输入新的值：已配置的项留空即表示保持不变。");
      return;
    }
    request("PUT", "/api/v1/api-config", { values: values })
      .then(function (data) {
        loadConfig();
        window.alert("已写入 " + data.env_file + "，密钥保存成功。部分客户端需重启开发服务后完全生效。");
      })
      .catch(function (error) { window.alert(error.message); });
  }

  function verifyCard(card, button) {
    var result = card.querySelector(".verify-result");
    button.disabled = true;
    result.textContent = "正在检测……";
    result.className = "verify-result pending";
    request("POST", "/api/v1/api-config/verify", { client_id: card.dataset.clientId })
      .then(function (data) {
        result.textContent = (data.ok ? "✅ " : "❌ ") + data.message;
        result.className = "verify-result " + (data.ok ? "ok" : "fail");
      })
      .catch(function (error) {
        result.textContent = "❌ " + error.message;
        result.className = "verify-result fail";
      })
      .finally(function () { button.disabled = false; });
  }

  function loadConfig() {
    request("GET", "/api/v1/api-config")
      .then(function (config) {
        renderBanner(config);
        render(listEl, config);
      })
      .catch(function (error) {
        listEl.textContent = "";
        listEl.appendChild(el("p", "config-loading", "配置状态加载失败：" + error.message));
      });
  }

  loadConfig();
})();
