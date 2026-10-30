/* 行程编辑：名称、站点时间/备注、站点上下移与删除。
   不做拖拽（无拖拽库）；保存走现有 PATCH，并带 expected_version 做并发保护。 */
(function () {
  "use strict";

  var container = document.getElementById("itinerary-editor-body");
  var dataEl = document.getElementById("itinerary-edit-data");
  if (!container || !dataEl) return;

  var data = JSON.parse(dataEl.textContent);
  var state = {
    version: data.version,
    title: data.title || "",
    days: data.days.map(function (day) {
      return {
        day_number: day.day_number,
        summary: day.summary,
        stops: day.stops.map(function (stop) { return Object.assign({}, stop); })
      };
    })
  };

  var statusEl = null;

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = text;
    return node;
  }

  function setStatus(text, isError) {
    if (!statusEl) return;
    statusEl.textContent = text || "";
    statusEl.classList.toggle("is-error", Boolean(isError));
  }

  function moveStop(dayIndex, index, offset) {
    var stops = state.days[dayIndex].stops;
    var target = index + offset;
    if (target < 0 || target >= stops.length) return;
    var moved = stops.splice(index, 1)[0];
    stops.splice(target, 0, moved);
    render();
  }

  function render() {
    container.textContent = "";

    var titleField = el("label", "editor-field", "行程名称");
    var titleInput = document.createElement("input");
    titleInput.type = "text";
    titleInput.maxLength = 255;
    titleInput.value = state.title;
    titleInput.addEventListener("input", function () { state.title = titleInput.value; });
    titleField.appendChild(titleInput);
    container.appendChild(titleField);

    state.days.forEach(function (day, dayIndex) {
      var fieldset = el("fieldset", "editor-day");
      fieldset.appendChild(el("legend", null, "第 " + day.day_number + " 天"));
      if (day.summary) fieldset.appendChild(el("p", "editor-day-summary", day.summary));

      day.stops.forEach(function (stop, index) {
        var row = el("div", "editor-stop");
        row.appendChild(el("span", "editor-stop-name", stop.name));

        var timeLabel = el("label", "editor-field", "时间");
        var timeInput = document.createElement("input");
        timeInput.type = "time";
        timeInput.value = stop.time_slot;
        timeInput.addEventListener("change", function () { stop.time_slot = timeInput.value; });
        timeLabel.appendChild(timeInput);
        row.appendChild(timeLabel);

        var noteLabel = el("label", "editor-field editor-note", "我的备注");
        var noteInput = document.createElement("textarea");
        noteInput.maxLength = 1000;
        noteInput.rows = 1;
        noteInput.value = stop.user_note || "";
        noteInput.addEventListener("input", function () { stop.user_note = noteInput.value; });
        noteLabel.appendChild(noteInput);
        row.appendChild(noteLabel);

        var actions = el("div", "editor-stop-actions");
        [["上移", -1], ["下移", 1]].forEach(function (pair) {
          var button = el("button", "secondary-button", pair[0]);
          button.type = "button";
          button.addEventListener("click", function () { moveStop(dayIndex, index, pair[1]); });
          actions.appendChild(button);
        });
        var remove = el("button", "secondary-button danger", "移除此站");
        remove.type = "button";
        remove.addEventListener("click", function () {
          if (!window.confirm("确认从第 " + day.day_number + " 天移除「" + stop.name + "」？")) return;
          day.stops.splice(index, 1);
          render();
        });
        actions.appendChild(remove);
        row.appendChild(actions);
        fieldset.appendChild(row);
      });

      if (!day.stops.length) fieldset.appendChild(el("p", "editor-empty", "当天暂无站点，可在下方保存后重新规划。"));
      container.appendChild(fieldset);
    });

    var saveBar = el("div", "editor-actions");
    var save = el("button", "primary-button", "保存修改");
    save.type = "button";
    save.addEventListener("click", saveIt);
    saveBar.appendChild(save);
    statusEl = el("p", "editor-status");
    statusEl.setAttribute("role", "status");
    statusEl.setAttribute("aria-live", "polite");
    saveBar.appendChild(statusEl);
    container.appendChild(saveBar);
  }

  function payload() {
    return {
      title: state.title.trim() || undefined,
      expected_version: state.version,
      days: state.days.map(function (day) {
        return {
          day_number: day.day_number,
          summary: day.summary,
          stops: day.stops.map(function (stop) {
            return {
              landmark_id: stop.landmark_id,
              time_slot: stop.time_slot,
              planned_minutes: stop.planned_minutes,
              selection_reason: stop.selection_reason,
              user_note: stop.user_note || null
            };
          })
        };
      })
    };
  }

  function saveIt() {
    setStatus("正在保存…");
    fetch("/api/v1/itineraries/" + data.id, {
      method: "PATCH",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload())
    })
      .then(function (response) {
        return response.json().then(function (body) { return { response: response, body: body }; });
      })
      .then(function (result) {
        if (result.response.ok) {
          window.location.reload();
          return;
        }
        if (result.response.status === 409) {
          setStatus("行程已在其他窗口更新，页面即将刷新，请重新确认改动。", true);
          window.setTimeout(function () { window.location.reload(); }, 1500);
          return;
        }
        var detail = result.body && result.body.detail;
        setStatus(typeof detail === "string" ? detail : "保存失败（" + result.response.status + "）", true);
      })
      .catch(function () { setStatus("网络异常，请稍后重试；你的输入仍保留在页面上。", true); });
  }

  render();
})();
