/* 认证状态区：全站 Header 用户状态 + 登录/注册表单逻辑。 */
(function () {
  "use strict";

  var ROLE_LABELS = { admin: "管理员", level1: "一级贡献者", level2: "二级用户" };

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function showAuthError(id, message) {
    var node = document.getElementById(id);
    if (node) node.textContent = message;
  }

  /** 只接受站内绝对路径，避免 ?next=//evil.com 之类开放重定向。 */
  function safeNext(value) {
    if (!value) return "/";
    var candidate = String(value).trim();
    if (candidate.charAt(0) !== "/" || candidate.indexOf("//") === 0) return "/";
    if (candidate.indexOf("\\") !== -1 || candidate.indexOf(":") !== -1) return "/";
    return candidate;
  }

  function nextTarget() {
    try {
      return safeNext(new URLSearchParams(window.location.search).get("next"));
    } catch (_) {
      return "/";
    }
  }

  function renderStatus(me) {
    var box = document.getElementById("auth-status");
    var authenticated = Boolean(me && me.authenticated);
    document.querySelectorAll(".admin-only").forEach(function (link) {
      link.style.display = authenticated && me.role === "admin" ? "" : "none";
    });
    // 未登录时不展示需要身份的入口，避免伪可用链接
    document.querySelectorAll(".account-link").forEach(function (link) {
      if (!link.classList.contains("admin-only")) link.style.display = authenticated ? "" : "none";
    });
    if (!box) return;
    box.innerHTML = "";
    if (!authenticated) {
      var login = el("a", "auth-link", "登录");
      login.href = "/login" + (window.location.pathname !== "/login" ? "?next=" + encodeURIComponent(window.location.pathname + window.location.search) : "");
      var register = el("a", "auth-link auth-register", "注册");
      register.href = "/register";
      box.appendChild(login);
      box.appendChild(register);
      return;
    }
    box.appendChild(el("span", "auth-badge role-" + me.role, ROLE_LABELS[me.role] || me.role));
    var profile = el("a", "auth-name", me.username || me.email);
    profile.href = "/account/api-keys";
    profile.title = "个人中心（密钥管理）";
    box.appendChild(profile);
    var logout = el("button", "auth-logout", "退出");
    logout.type = "button";
    logout.addEventListener("click", function () {
      logout.disabled = true;
      fetch("/api/v1/auth/logout", { method: "POST" })
        .then(function () { window.location.reload(); })
        .catch(function () { logout.disabled = false; });
    });
    box.appendChild(logout);
  }

  function loadStatus() {
    fetch("/api/v1/auth/me", { headers: { Accept: "application/json" } })
      .then(function (resp) { return resp.json(); })
      .then(renderStatus)
      .catch(function () { /* 网络异常时保留默认渲染 */ });
  }

  var submitting = false;

  function submitAuth(url, body, errorId, button) {
    if (submitting) return;
    submitting = true;
    if (button) { button.disabled = true; button.setAttribute("aria-busy", "true"); }
    var release = function () {
      submitting = false;
      if (button) { button.disabled = false; button.removeAttribute("aria-busy"); }
    };
    fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    })
      .then(function (resp) {
        return resp.json().then(function (data) { return { ok: resp.ok, status: resp.status, data: data }; });
      })
      .then(function (result) {
        if (!result.ok) {
          var parse = (window.apiErrors && window.apiErrors.parse);
          showAuthError(errorId, parse ? parse(result.data, "操作失败，请稍后再试。") : "操作失败，请稍后再试。");
          release();
          return;
        }
        // 只有服务端明确返回成功才跳转；网络或校验失败都不显示为成功
        window.location.href = nextTarget();
      })
      .catch(function () {
        showAuthError(errorId, "网络异常，未完成登录/注册，请稍后重试。");
        release();
      });
  }

  function bindAuthForms() {
    var loginForm = document.getElementById("login-form");
    if (loginForm) {
      loginForm.addEventListener("submit", function (event) {
        event.preventDefault();
        submitAuth("/api/v1/auth/login", {
          username: document.getElementById("login-username").value,
          password: document.getElementById("login-password").value,
        }, "login-error", loginForm.querySelector("button[type=submit]"));
      });
    }
    var registerForm = document.getElementById("register-form");
    if (registerForm) {
      registerForm.addEventListener("submit", function (event) {
        event.preventDefault();
        var password = document.getElementById("register-password").value;
        var confirm = document.getElementById("register-confirm").value;
        if (password !== confirm) {
          showAuthError("register-error", "两次输入的密码不一致。");
          return;
        }
        submitAuth("/api/v1/auth/register", {
          username: document.getElementById("register-username").value,
          email: document.getElementById("register-email").value,
          password: password,
        }, "register-error", registerForm.querySelector("button[type=submit]"));
      });
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    loadStatus();
    bindAuthForms();
  });
})();
