/* 认证状态区：全站 Header 用户状态 + 登录/注册表单逻辑。 */
(function () {
  "use strict";

  var ROLE_LABELS = { admin: "管理员", level1: "一级用户", level2: "二级用户" };

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

  function renderStatus(me) {
    var box = document.getElementById("auth-status");
    if (!box) return;
    // 管理后台入口仅管理员可见
    var adminNav = document.querySelectorAll(".site-nav .admin-only");
    adminNav.forEach(function (link) { link.style.display = me && me.authenticated && me.role === "admin" ? "" : "none"; });
    box.innerHTML = "";
    if (!me || !me.authenticated) {
      var login = el("a", "auth-link", "登录");
      login.href = "/login";
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
      fetch("/api/v1/auth/logout", { method: "POST" }).then(function () { window.location.reload(); });
    });
    box.appendChild(logout);
  }

  function loadStatus() {
    fetch("/api/v1/auth/me", { headers: { Accept: "application/json" } })
      .then(function (resp) { return resp.json(); })
      .then(renderStatus)
      .catch(function () { /* 网络异常时保留默认渲染 */ });
  }

  function submitAuth(url, body, errorId) {
    fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    })
      .then(function (resp) {
        return resp.json().then(function (data) { return { ok: resp.ok, data: data }; });
      })
      .then(function (result) {
        if (!result.ok) {
          var detail = result.data && result.data.detail;
          showAuthError(errorId, typeof detail === "string" ? detail : "操作失败，请稍后再试。");
          return;
        }
        window.location.href = "/";
      })
      .catch(function () { showAuthError(errorId, "网络异常，请稍后再试。"); });
  }

  function bindAuthForms() {
    var loginForm = document.getElementById("login-form");
    if (loginForm) {
      loginForm.addEventListener("submit", function (event) {
        event.preventDefault();
        submitAuth("/api/v1/auth/login", {
          username: document.getElementById("login-username").value,
          password: document.getElementById("login-password").value,
        }, "login-error");
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
        }, "register-error");
      });
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    loadStatus();
    bindAuthForms();
  });
})();
