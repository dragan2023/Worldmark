/* 地标相册多图编辑组件：工作集 = 已发布照片 + 暂存（上传/AI）照片。
   交互：点击小图放大预览并编辑元数据；右上角 × 移除；提交时统一落库。 */
(function () {
  "use strict";

  var landmarkId = document.body.dataset.landmarkId;
  var grid = document.getElementById("album-grid");
  var statusEl = document.getElementById("album-status");
  var errorEl = document.getElementById("album-error");
  var uploadInput = document.getElementById("album-upload-input");
  var aiButton = document.getElementById("album-ai-button");
  var submitButton = document.getElementById("album-submit-button");
  var lightbox = document.getElementById("album-lightbox");
  var lightboxImage = document.getElementById("lightbox-image");
  var lightboxForm = document.getElementById("lightbox-form");

  var KIND_LABELS = { published: "已发布", upload: "待提交", ai: "AI 下载" };
  var workingSet = []; // {kind, file, url, alt, caption, credit, license, source_url, removed}
  var editingIndex = -1;
  var busy = false;

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = text;
    return node;
  }

  function request(method, url, body) {
    var options = { method: method };
    if (body instanceof FormData) {
      options.body = body;
    } else if (body !== undefined) {
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

  function setStatus(text) { statusEl.textContent = text || ""; }
  function setError(text) { errorEl.textContent = text || ""; }

  function setBusy(flag) {
    busy = flag;
    uploadInput.disabled = flag;
    aiButton.disabled = flag;
    submitButton.disabled = flag;
  }

  function itemKey(item) { return item.kind + ":" + item.file; }

  function render() {
    grid.textContent = "";
    if (!workingSet.length) {
      grid.appendChild(el("p", "editor-loading", "相册还是空的：上传图片，或点「AI 找图」让 AI 检索候选图片。"));
      return;
    }
    workingSet.forEach(function (item, index) {
      grid.appendChild(renderTile(item, index));
    });
  }

  function renderTile(item, index) {
    var tile = el("figure", "album-tile" + (item.removed ? " is-removed" : ""));
    tile.dataset.index = String(index);

    var image = el("img", "album-thumb");
    image.src = item.url;
    image.alt = item.alt || item.file;
    image.loading = "lazy";
    tile.appendChild(image);

    tile.appendChild(el("span", "album-tile-badge kind-" + item.kind, KIND_LABELS[item.kind] || item.kind));

    if (item.removed) {
      var undo = el("button", "album-tile-undo", "撤销删除");
      undo.type = "button";
      undo.addEventListener("click", function (event) {
        event.stopPropagation();
        item.removed = false;
        render();
      });
      tile.appendChild(undo);
      tile.appendChild(el("span", "album-tile-removed-tip", "提交后将从相册移除"));
      return tile;
    }

    var remove = el("button", "album-tile-remove", "×");
    remove.type = "button";
    remove.title = item.kind === "published" ? "从相册移除" : "取消这张图片";
    remove.setAttribute("aria-label", "移除图片");
    remove.addEventListener("click", function (event) {
      event.stopPropagation();
      removeItem(item, index);
    });
    tile.appendChild(remove);

    tile.addEventListener("click", function () { openLightbox(index); });
    return tile;
  }

  function removeItem(item, index) {
    setError("");
    if (item.kind === "published") {
      item.removed = true;
      render();
      return;
    }
    setBusy(true);
    setStatus("正在移除暂存图片……");
    request("DELETE", "/api/v1/landmarks/" + landmarkId + "/album/editor/staged/" + encodeURIComponent(item.file))
      .then(function () {
        workingSet.splice(index, 1);
        setStatus("已移除。");
        render();
      })
      .catch(function (error) { setError(error.message); })
      .finally(function () { setBusy(false); });
  }

  // ---------- 灯箱：大图预览 + 元数据编辑 ----------

  function openLightbox(index) {
    editingIndex = index;
    var item = workingSet[index];
    if (!item) return;
    lightboxImage.src = item.url;
    lightboxImage.alt = item.alt || "";
    document.getElementById("field-alt").value = item.alt || "";
    document.getElementById("field-caption").value = item.caption || "";
    document.getElementById("field-credit").value = item.credit || "";
    document.getElementById("field-license").value = item.license || "";
    document.getElementById("field-source").value = item.source_url || "";
    lightbox.showModal();
  }

  lightboxForm.addEventListener("submit", function (event) {
    event.preventDefault();
    if (editingIndex < 0) return;
    var alt = document.getElementById("field-alt").value.trim();
    if (!alt) {
      setError("图片说明（alt）不能为空。");
      return;
    }
    var item = workingSet[editingIndex];
    item.alt = alt;
    item.caption = document.getElementById("field-caption").value.trim() || null;
    item.credit = document.getElementById("field-credit").value.trim() || null;
    item.license = document.getElementById("field-license").value.trim();
    item.source_url = document.getElementById("field-source").value.trim() || null;
    lightbox.close();
    render();
    setStatus("已保存图片信息（提交相册前不会对外展示）。");
  });

  document.getElementById("lightbox-close").addEventListener("click", function () { lightbox.close(); });

  // ---------- 上传 ----------

  uploadInput.addEventListener("change", function () {
    if (!uploadInput.files || !uploadInput.files.length) return;
    setError("");
    var form = new FormData();
    Array.prototype.forEach.call(uploadInput.files, function (file) { form.append("files", file); });
    setBusy(true);
    setStatus("正在上传 " + uploadInput.files.length + " 张图片……");
    request("POST", "/api/v1/landmarks/" + landmarkId + "/album/editor/uploads", form)
      .then(function (data) {
        data.saved.forEach(function (photo) { workingSet.push(photo); });
        setStatus("已上传 " + data.saved.length + " 张。" + (data.errors.length ? "有 " + data.errors.length + " 张失败。" : ""));
        if (data.errors.length) setError(data.errors.map(function (item) { return item.file + "：" + item.reason; }).join("；"));
        render();
      })
      .catch(function (error) { setError(error.message); })
      .finally(function () {
        setBusy(false);
        uploadInput.value = "";
      });
  });

  // ---------- AI 找图 ----------

  aiButton.addEventListener("click", function () {
    setError("");
    setBusy(true);
    setStatus("AI 正在生成检索词、搜索并下载图片……约需 10-40 秒。");
    request("POST", "/api/v1/landmarks/" + landmarkId + "/album/editor/ai-download")
      .then(function (data) {
        data.saved.forEach(function (photo) { workingSet.push(photo); });
        var lines = [];
        if (data.saved.length) lines.push("AI 已下载 " + data.saved.length + " 张候选图片，请检查内容与版权信息，不满意的直接 × 掉。");
        if (data.failures.length) lines.push(data.failures.length + " 张下载失败。");
        (data.notices || []).forEach(function (notice) { lines.push(notice); });
        setStatus(lines.join(" ") + " 检索词：" + data.queries.join(" / "));
        if (data.failures.length) {
          setError(data.failures.slice(0, 3).map(function (item) { return item.reason; }).join("；"));
        }
        render();
      })
      .catch(function (error) { setError(error.message); })
      .finally(function () { setBusy(false); });
  });

  // ---------- 提交落库 ----------

  submitButton.addEventListener("click", function () {
    setError("");
    var payload = workingSet
      .filter(function (item) { return !item.removed; })
      .map(function (item) {
        return {
          kind: item.kind,
          file: item.file,
          alt: (item.alt || "").trim(),
          caption: item.caption,
          credit: item.credit,
          license: item.license,
          source_url: item.source_url,
        };
      });
    if (!payload.length) {
      setError("相册为空：请至少保留或上传一张图片。");
      return;
    }
    var missingAlt = payload.filter(function (item) { return !item.alt; });
    if (missingAlt.length) {
      setError("有 " + missingAlt.length + " 张图片缺少说明，点击小图补填后再提交。");
      return;
    }
    if (!window.confirm("确认提交相册？提交后立即对外展示（共 " + payload.length + " 张）。")) return;
    setBusy(true);
    setStatus("正在提交相册……");
    request("POST", "/api/v1/landmarks/" + landmarkId + "/album/submit", { photos: payload })
      .then(function (data) {
        var note = data.review_note ? " " + data.review_note : "";
        setStatus("提交完成：新增 " + data.added_count + " 张、移除 " + data.removed_count + " 张，现共 " + data.published_count + " 张已发布。" + note);
        loadEditor();
      })
      .catch(function (error) { setError(error.message); })
      .finally(function () { setBusy(false); });
  });

  // ---------- 初始化 ----------

  function loadEditor() {
    request("GET", "/api/v1/landmarks/" + landmarkId + "/album/editor")
      .then(function (data) {
        workingSet = (data.published || []).concat(data.staged || []);
        render();
      })
      .catch(function (error) {
        grid.textContent = "";
        if (error.message.indexOf("贡献者") !== -1 || error.message.indexOf("管理员") !== -1 || error.message.indexOf("登录") !== -1) {
          // 非贡献者/管理员：隐藏编辑控件，仅浏览
          if (uploadInput && uploadInput.closest(".album-editor-controls")) uploadInput.closest(".album-editor-controls").style.display = "none";
          if (aiButton) aiButton.style.display = "none";
          if (submitButton) submitButton.style.display = "none";
          grid.appendChild(el("p", "editor-loading", error.message));
          setError("");
          return;
        }
        grid.appendChild(el("p", "editor-loading", "加载失败：" + error.message));
      });
  }

  loadEditor();
})();
