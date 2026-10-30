# tests/e2e —— 进程内流程回归（不是浏览器测试）

这些用例通过 FastAPI/Starlette 的 **`TestClient`** 在**同一进程内**调用应用：

- 覆盖「目录 → 详情 → 行程」「登录 → 权限」「会员/地图访问」等跨模块业务链路；
- 不启动 uvicorn、不启动浏览器，因此**不能**证明 CSS/JS、响应式布局、键盘操作、对比度或真实瓦片加载正确；
- 数据库是 `tmp_path` 下的临时 SQLite，外部服务使用替身，凭据环境变量被清空。

需要真实浏览器证据时，使用项目根目录的：

```powershell
.\.venv\Scripts\python.exe scripts\run_browser_smoke.py --out 测试证据\项目改进实施20261022\browser
```

它由 `scripts/run_browser_smoke.py` 拉起隔离 uvicorn 与临时库，再执行 `tests/browser/smoke.mjs`（真实 Chromium），
结果写入 `browser-smoke.json` 与按视口命名的截图。命名上的区别：`e2e` = 端到端业务链路回归，`browser` = 真实渲染验证。
