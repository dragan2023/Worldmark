/* 一键入库页交互：提交自然语言输入，渲染 AI 生成的候选地标条目 */
(function () {
  "use strict";

  var form = document.getElementById("intake-form");
  var input = document.getElementById("intake-input");
  var submitBtn = document.getElementById("intake-submit");
  var statusEl = document.getElementById("intake-status");
  var errorEl = document.getElementById("intake-error");
  var resultEl = document.getElementById("intake-result");

  var STEP_LABELS = {
    parse: "解析输入",
    research: "联网核实",
    compose: "生成条目",
    ground: "解析坐标",
    persist: "入库",
  };
  var STEP_STATUS_LABELS = { ok: "完成", skipped: "跳过", failed: "失败" };

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = text;
    return node;
  }

  document.querySelectorAll(".example-chip").forEach(function (chip) {
    chip.addEventListener("click", function () {
      input.value = chip.textContent.trim();
      input.focus();
    });
  });

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    var text = input.value.trim();
    if (!text) {
      errorEl.textContent = "请先输入作品名与地标名。";
      return;
    }
    submitBtn.disabled = true;
    errorEl.textContent = "";
    resultEl.classList.add("hidden");
    resultEl.textContent = "";
    statusEl.textContent = "AI 正在解析输入、核实资料并生成条目……约需 10-40 秒，请勿关闭页面。";

    fetch("/api/v1/agent/landmarks/intake", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ input: text }),
    })
      .then(function (response) {
        return response.json().then(function (data) {
          if (!response.ok) {
            var detail = data && data.detail ? data.detail : "请求失败（" + response.status + "）";
            throw Object.assign(new Error(typeof detail === "string" ? detail : JSON.stringify(detail)), {
              status: response.status,
            });
          }
          return data;
        });
      })
      .then(function (data) {
        statusEl.textContent = "";
        renderResult(data);
      })
      .catch(function (error) {
        statusEl.textContent = "";
        if (error.status === 503) {
          errorEl.textContent = error.message + " ";
          var link = el("a", null, "前往 API 配置页");
          link.href = "/settings/api";
          errorEl.appendChild(link);
        } else {
          errorEl.textContent = error.message;
        }
      })
      .finally(function () {
        submitBtn.disabled = false;
      });
  });

  function renderResult(data) {
    resultEl.classList.remove("hidden");
    resultEl.textContent = "";

    var head = el("div", "result-head");
    var titleBox = el("div", "result-title");
    titleBox.appendChild(el("h2", null, data.landmark_name));
    titleBox.appendChild(el("p", "result-subtitle", "《" + data.work_title + "》 · " + ipTypeLabel(data.ip_type)));
    head.appendChild(titleBox);
    head.appendChild(el("span", "badge result-badge", "候选待审核"));
    resultEl.appendChild(head);

    var facts = el("dl", "result-facts");
    addFact(facts, "现实地址", data.address);
    addFact(
      facts,
      "坐标",
      data.latitude !== null && data.latitude !== undefined
        ? data.latitude.toFixed(6) + ", " + data.longitude.toFixed(6) + "（WGS-84）"
        : "未能解析（已留空待人工补全）"
    );
    addFact(facts, "来源", "");
    resultEl.appendChild(facts);

    var sourceLink = el("a", "result-source", data.source_url);
    sourceLink.href = data.source_url;
    sourceLink.target = "_blank";
    sourceLink.rel = "noopener";
    resultEl.querySelector(".result-facts").appendChild(sourceLink);

    var descBox = el("div", "result-description");
    descBox.appendChild(el("h3", null, "三段式简介"));
    data.description.split("\n").forEach(function (paragraph) {
      if (paragraph.trim()) descBox.appendChild(el("p", null, paragraph.trim()));
    });
    resultEl.appendChild(descBox);

    if (data.warnings && data.warnings.length) {
      var warnBox = el("div", "result-warnings");
      warnBox.appendChild(el("h3", null, "⚠️ 需要注意"));
      data.warnings.forEach(function (warning) {
        warnBox.appendChild(el("p", null, warning));
      });
      resultEl.appendChild(warnBox);
    }

    var stepsBox = el("details", "result-steps");
    stepsBox.appendChild(el("summary", null, "查看 AI 执行过程"));
    var stepsList = el("ul");
    (data.steps || []).forEach(function (step) {
      stepsList.appendChild(
        el(
          "li",
          null,
          (STEP_LABELS[step.name] || step.name) +
            "：" +
            (STEP_STATUS_LABELS[step.status] || step.status) +
            (step.detail ? "（" + step.detail + "）" : "")
        )
      );
    });
    stepsBox.appendChild(stepsList);
    resultEl.appendChild(stepsBox);

    resultEl.appendChild(el("p", "result-review-note", data.review_note || ""));

    var actions = el("div", "result-actions");
    var detailLink = el("a", "primary-button", "查看地标详情");
    detailLink.href = data.detail_url;
    actions.appendChild(detailLink);
    var albumLink = el("a", "ghost-button result-album-link", "管理相册");
    albumLink.href = "/landmarks/" + data.landmark_id + "/album/edit";
    actions.appendChild(albumLink);
    var againBtn = el("button", "ghost-button", "继续录入下一条");
    againBtn.type = "button";
    againBtn.addEventListener("click", function () {
      resultEl.classList.add("hidden");
      input.value = "";
      input.focus();
    });
    actions.appendChild(againBtn);
    resultEl.appendChild(actions);
  }

  function addFact(dl, label, value) {
    var dt = el("dt", null, label);
    var dd = el("dd", null, value);
    dl.appendChild(dt);
    dl.appendChild(dd);
  }

  function ipTypeLabel(value) {
    return { literature: "文学", game: "游戏", screen: "影视" }[value] || value;
  }
})();
