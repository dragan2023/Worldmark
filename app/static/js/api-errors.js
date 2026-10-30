/* 统一解析后端错误：字符串 detail、对象 code、Pydantic 错误数组与网络错误。 */
(function () {
  "use strict";

  function parse(body, fallback) {
    var detail = body && body.detail;
    if (typeof detail === "string" && detail.trim()) return detail;
    if (Array.isArray(detail)) {
      var messages = detail
        .map(function (item) {
          if (!item) return null;
          var field = Array.isArray(item.loc) ? item.loc.filter(function (part) { return part !== "body"; }).join(".") : "";
          return (field ? field + "：" : "") + (item.msg || "输入有误");
        })
        .filter(Boolean);
      if (messages.length) return messages.join("；");
    }
    if (detail && typeof detail === "object") {
      return detail.message || detail.code || fallback || "请求失败";
    }
    if (body && typeof body.message === "string") return body.message;
    return fallback || "请求失败，请稍后重试。";
  }

  function isNetworkError(error) {
    return !error || error.name === "TypeError" || /Failed to fetch|NetworkError/i.test(String(error.message || ""));
  }

  window.apiErrors = { parse: parse, isNetworkError: isNetworkError };
})();
