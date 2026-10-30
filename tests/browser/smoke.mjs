/**
 * 真实浏览器冒烟：首页搜索、搜索分页、地图输入/过滤/重置、登录返回、地标选择器翻页、
 * 基础行程生成/编辑/导出、我的贡献记录，以及 360/390/768/1280/1440 视口的横向溢出、
 * 文本对比度与触控目标尺寸实测。
 *
 * 由 scripts/run_browser_smoke.py 启动隔离服务后调用：
 *   node tests/browser/smoke.mjs --base-url http://127.0.0.1:PORT --out 测试证据/xxx
 */
import { createRequire } from "node:module";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";

// Playwright 只作为测试依赖装在托管 Node 工作区，用绝对路径加载，不进入项目运行环境。
const require = createRequire(import.meta.url);
const playwrightPath = process.env.PLAYWRIGHT_MODULE || "playwright";
const engines = require(playwrightPath);
const engineName = (process.env.BROWSER_ENGINE || "chromium").toLowerCase();
const engine = engines[engineName];
if (!engine) throw new Error("Unsupported BROWSER_ENGINE: " + engineName);

const args = process.argv.slice(2);
const option = (name, fallback) => {
  const index = args.indexOf(`--${name}`);
  return index === -1 ? fallback : args[index + 1];
};

const baseUrl = option("base-url", "http://127.0.0.1:8000");
const outDir = option("out", ".");
const username = option("username", "smoke_user");
const password = option("password", "smoke-password-123");
const landmarkId = option("landmark-id", "1");

mkdirSync(outDir, { recursive: true });

const results = [];
const consoleErrors = [];
let failureCount = 0;

const record = (name, ok, detail) => {
  results.push({ name, ok, detail });
  if (!ok) failureCount += 1;
  console.log(`${ok ? "PASS" : "FAIL"} ${name}${detail ? " · " + detail : ""}`);
};

const attachDiagnostics = (page, label) => {
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push({ page: label, message: message.text() });
  });
  page.on("pageerror", (error) => consoleErrors.push({ page: label, message: `pageerror: ${error.message}` }));
};

const horizontalOverflow = (page) =>
  page.evaluate(() => ({
    scrollWidth: document.scrollingElement.scrollWidth,
    innerWidth: window.innerWidth,
  }));

// 逐元素计算「文字颜色 vs 实际背景」的对比度，只统计正文尺寸的文字（WCAG 1.4.3：4.5:1）
const contrastReport = (page) =>
  page.evaluate(() => {
    const parse = (value) => {
      const match = /rgba?\(([^)]+)\)/.exec(value || "");
      if (!match) return null;
      const parts = match[1].split(",").map((item) => parseFloat(item.trim()));
      return { r: parts[0], g: parts[1], b: parts[2], a: parts.length > 3 ? parts[3] : 1 };
    };
    const luminance = ({ r, g, b }) => {
      const channel = (value) => (value / 255 <= 0.03928 ? value / 255 / 12.92 : Math.pow((value / 255 + 0.055) / 1.055, 2.4));
      return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
    };
    const ratio = (first, second) => {
      const a = luminance(first);
      const b = luminance(second);
      return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
    };
    const blend = (top, bottom) => ({
      r: top.r * top.a + bottom.r * (1 - top.a),
      g: top.g * top.a + bottom.g * (1 - top.a),
      b: top.b * top.a + bottom.b * (1 - top.a),
      a: 1,
    });
    // 自下而上叠加所有祖先背景色，再叠加元素自身背景，得到真实渲染底色
    const background = (element) => {
      const stack = [];
      let node = element;
      while (node) {
        const color = parse(getComputedStyle(node).backgroundColor);
        if (color && color.a > 0) stack.push(color);
        node = node.parentElement;
      }
      let base = { r: 255, g: 255, b: 255, a: 1 };
      for (let index = stack.length - 1; index >= 0; index -= 1) base = blend(stack[index], base);
      return base;
    };
    // 背景为渐变且尚无实色底色时，纯色计算不可靠，标记为无法测量而不是编造数值
    const gradientOnPath = (element) => {
      let node = element;
      while (node) {
        const style = getComputedStyle(node);
        const color = parse(style.backgroundColor);
        if (color && color.a >= 0.95) return false;
        if (style.backgroundImage && style.backgroundImage !== "none") return true;
        node = node.parentElement;
      }
      return false;
    };
    let checked = 0;
    let unmeasuredGradient = 0;
    let worst = { ratio: 99 };
    const offenders = [];
    for (const element of document.querySelectorAll("body *")) {
      if (checked > 800) break;
      if (!element.getClientRects().length) continue;
      if (element.closest(".is-disabled, [disabled], [aria-disabled='true']")) continue;
      if (gradientOnPath(element)) { unmeasuredGradient += 1; continue; }
      const hasText = [...element.childNodes].some((node) => node.nodeType === 3 && node.textContent.trim().length > 1);
      if (!hasText) continue;
      const style = getComputedStyle(element);
      if (parseFloat(style.opacity) < 0.9) continue;
      const size = parseFloat(style.fontSize);
      const weight = parseInt(style.fontWeight, 10) || 400;
      if (size >= 24 || (size >= 18.66 && weight >= 700)) continue; // 大字阈值 3:1
      const color = parse(style.color);
      if (!color) continue;
      checked += 1;
      const backdrop = background(element);
      const value = Number(ratio(blend(color, backdrop), backdrop).toFixed(2));
      const text = (element.textContent || "").trim().slice(0, 24);
      const className = typeof element.className === "string" ? element.className.split(" ")[0] : "";
      const selector = element.tagName.toLowerCase() + (className ? "." + className : "");
      if (value < worst.ratio) worst = { ratio: value, text, selector, fontSize: size };
      if (value < 4.5) offenders.push({ ratio: value, text, color: style.color, fontSize: size });
    }
    return { checked, unmeasuredGradient, worst, offenders: offenders.slice(0, 5) };
  });

// 实测触控目标尺寸（WCAG 2.5.8 / 项目 44×44 设计目标）
const targetReport = (page, selectors) =>
  page.evaluate((list) => list.map((selector) => {
    const elements = [...document.querySelectorAll(selector)].filter((element) => element.getClientRects().length);
    if (!elements.length) return { selector, count: 0 };
    const sizes = elements.map((element) => {
      const rect = element.getBoundingClientRect();
      return { width: Math.round(rect.width), height: Math.round(rect.height) };
    });
    return {
      selector,
      count: elements.length,
      minWidth: Math.min(...sizes.map((size) => size.width)),
      minHeight: Math.min(...sizes.map((size) => size.height)),
    };
  }), selectors);

const AXE_PATH = process.env.AXE_MODULE || "";
const axeSource = AXE_PATH ? readFileSync(AXE_PATH, "utf-8") : "";
const axeResults = [];

// 真实的自动化无障碍审计（axe-core，WCAG 2.0/2.1 A+AA）。它不是读屏软件，
// 但覆盖了可访问名称、角色、标签、对比度等读屏依赖的机器可判定项。
const runAxe = async (target, label) => {
  if (!axeSource) return;
  try {
    await target.addScriptTag({ content: axeSource });
    const violations = await target.evaluate(async () => {
      const report = await window.axe.run(document, {
        runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"] },
      });
      return report.violations.map((item) => ({
        id: item.id,
        impact: item.impact,
        nodes: item.nodes.length,
        help: item.help,
      }));
    });
    axeResults.push({ page: label, violations });
    const serious = violations.filter((item) => item.impact === "serious" || item.impact === "critical");
    record(
      "axe " + label + " 无严重/致命无障碍违规",
      serious.length === 0,
      JSON.stringify(violations.slice(0, 6)),
    );
  } catch (error) {
    record("axe " + label + " 注入失败", false, error.message);
  }
};

const browser = await engine.launch();

try {
  // ---------------------------------------------------------------- 桌面流程
  const desktop = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page = await desktop.newPage();
  attachDiagnostics(page, "desktop");

  await page.goto(`${baseUrl}/`, { waitUntil: "networkidle" });
  await page.screenshot({ path: join(outDir, "desktop-home.png"), fullPage: true });
  const heroSearch = await page.locator(".home-search input[name=q]").count();
  record("首页首屏有搜索框", heroSearch > 0);
  await runAxe(page, "首页");

  await page.locator(".home-search input[name=q]").first().fill("应县");
  await page.locator(".home-search button[type=submit]").first().click();
  await page.waitForLoadState("networkidle");
  record("搜索页有结果", (await page.locator(".landmark-card").count()) > 0, page.url());
  await page.screenshot({ path: join(outDir, "desktop-search.png"), fullPage: true });

  const firstCard = page.locator(".landmark-card .card-title a").first();
  const landmarkName = (await firstCard.textContent())?.trim();
  await firstCard.click();
  await page.waitForLoadState("networkidle");
  record("详情页打开", (await page.locator("h1").first().textContent())?.includes(landmarkName ?? "###"));
  const joinLink = page.locator(".detail-actions a", { hasText: "加入行程" });
  record("详情页有加入行程主操作", (await joinLink.count()) === 1);
  await page.screenshot({ path: join(outDir, "desktop-detail.png"), fullPage: true });
  await runAxe(page, "详情页");

  await joinLink.click();
  await page.waitForLoadState("networkidle");
  record(
    "匿名点加入行程跳登录并带 next",
    page.url().includes("/login") && page.url().includes("next="),
    page.url(),
  );

  // ------------------------------------------------------------ 登录后流程
  await page.locator("#login-username").fill(username);
  await page.locator("#login-password").fill(password);
  await page.locator("#login-form button[type=submit]").click();
  await page.waitForURL((url) => url.pathname === "/itineraries/new", { timeout: 20000 });
  await page.waitForLoadState("networkidle");
  const afterLogin = new URL(page.url());
  record(
    "登录后回到原任务页",
    afterLogin.pathname === "/itineraries/new" && afterLogin.searchParams.get("landmark_id") !== null,
    page.url(),
  );

  let preselectChips = 0;
  try {
    await page.waitForSelector("#selected-landmarks .selected-chip", { timeout: 5000 });
    preselectChips = await page.locator("#selected-landmarks .selected-chip").count();
  } catch (_) {
    preselectChips = 0;
  }
  record("新建行程页预选地标", preselectChips === 1, `chips=${preselectChips}`);

  // 地标选择器：超过 50 条时的翻页、跨页保留选择、Esc 关闭
  await page.locator("#open-landmark-picker").click();
  await page.waitForSelector("#landmark-options .landmark-option", { timeout: 15000 });
  const pickerFirstPage = await page.locator("#landmark-options .landmark-option").count();
  const pickerPageInfo = await page.locator("#landmark-page-info").textContent();
  record(
    "选择器首页列出 50 条且可翻页",
    pickerFirstPage === 50 && (await page.locator("#landmark-next").isEnabled()),
    `${pickerFirstPage} 条 · ${pickerPageInfo}`,
  );
  await page.locator("#landmark-options .landmark-option input[type=checkbox]").first().check();
  const chipsAfterPick = await page.locator("#selected-landmarks .selected-chip").count();
  await page.locator("#landmark-next").click();
  await page.waitForFunction(
    () => (document.querySelector("#landmark-page-info")?.textContent || "").includes("第 2 / 2 页"),
    null,
    { timeout: 15000 },
  );
  const chipsAfterPage = await page.locator("#selected-landmarks .selected-chip").count();
  record("选择器翻页保留已选地标", chipsAfterPick === 2 && chipsAfterPage === 2, `chips ${chipsAfterPick} -> ${chipsAfterPage}`);

  await page.keyboard.press("Escape");
  await page.waitForTimeout(200);
  record("Esc 关闭地标选择弹窗", !(await page.locator("#landmark-dialog").evaluate((node) => node.open)));
  const extraChip = page.locator("#selected-landmarks .selected-chip .chip-remove").last();
  if (await extraChip.count()) await extraChip.click();
  record("移除已选地标后恢复为预选项", (await page.locator("#selected-landmarks .selected-chip").count()) === 1);

  await page.locator("input[name=start_date]").fill("2026-11-02");
  await page.locator("input[name=end_date]").fill("2026-11-03");
  await page.locator("input[name=origin_city]").fill("朔州");
  await page.screenshot({ path: join(outDir, "desktop-itinerary-form.png"), fullPage: true });
  await runAxe(page, "行程表单");

  await Promise.all([
    page.waitForURL(/\/itineraries\/\d+/, { timeout: 30000 }),
    page.locator("#preview-button").click(),
  ]);
  await page.waitForLoadState("networkidle");
  record("基础规划生成成功", /\/itineraries\/\d+/.test(page.url()), page.url());
  await page.screenshot({ path: join(outDir, "desktop-itinerary-detail.png"), fullPage: true });

  // 编辑：改名称 + 备注并保存
  await page.locator("#itinerary-editor details summary").click();
  const titleInput = page.locator("#itinerary-editor input[type=text]").first();
  await titleInput.fill("浏览器冒烟行程");
  const noteInput = page.locator("#itinerary-editor textarea").first();
  if (await noteInput.count()) await noteInput.fill("实测备注");
  await page.locator("#itinerary-editor button", { hasText: "保存修改" }).click();
  await page.waitForLoadState("networkidle");
  await page.waitForTimeout(600);
  record("编辑保存后标题已更新", (await page.locator("h1").first().textContent())?.includes("浏览器冒烟行程"));

  const itineraryContrast = await contrastReport(page);
  record(
    "行程详情页正文对比度 ≥4.5:1",
    itineraryContrast.checked > 0 && itineraryContrast.offenders.length === 0,
    `checked=${itineraryContrast.checked} worst=${JSON.stringify(itineraryContrast.worst)}${itineraryContrast.offenders.length ? " 低于阈值: " + JSON.stringify(itineraryContrast.offenders) : ""}`,
  );

  // 导出三种格式
  for (const format of ["html", "docx", "xlsx"]) {
    const response = await desktop.request.get(
      `${baseUrl}/api/v1/itineraries/${page.url().split("/").pop()}/exports/${format}`,
    );
    record(`导出 ${format.toUpperCase()}`, response.status() === 200, `status=${response.status()}`);
  }

  // 共创页对比度（金色状态徽章等）
  await page.goto(`${baseUrl}/intake`, { waitUntil: "networkidle" });
  const intakeContrast = await contrastReport(page);
  record(
    "共创页正文对比度 ≥4.5:1",
    intakeContrast.checked > 0 && intakeContrast.offenders.length === 0,
    `checked=${intakeContrast.checked} worst=${JSON.stringify(intakeContrast.worst)}${intakeContrast.offenders.length ? " 低于阈值: " + JSON.stringify(intakeContrast.offenders) : ""}`,
  );

  // 我的贡献记录
  await page.goto(`${baseUrl}/contributions`, { waitUntil: "networkidle" });
  const records = await page.locator(".contribution-record").count();
  record("我的贡献记录可见", records >= 1, `records=${records}`);
  await runAxe(page, "我的贡献");
  await page.screenshot({ path: join(outDir, "desktop-contributions.png"), fullPage: true });

  // 搜索分页：结果超过一页时仍可访问后续结果，超页回到有效页
  await page.goto(`${baseUrl}/search?q=测试地标`, { waitUntil: "networkidle" });
  const searchFirstPage = await page.locator(".landmark-card").count();
  const nextPageLink = page.locator(".pagination a.page-link", { hasText: "下一页" });
  record("搜索分页首页 20 条", searchFirstPage === 20, `cards=${searchFirstPage}`);
  record("搜索超过 20 条出现下一页入口", (await nextPageLink.count()) === 1);
  await nextPageLink.first().click();
  await page.waitForLoadState("networkidle");
  const secondPageCards = await page.locator(".landmark-card").count();
  record("搜索第 2 页可访问到后续结果", secondPageCards > 0 && page.url().includes("page=2"), `${secondPageCards} 条 · ${page.url()}`);
  await page.screenshot({ path: join(outDir, "desktop-search-page2.png"), fullPage: true });
  await page.goto(`${baseUrl}/search?q=测试地标&page=99`, { waitUntil: "networkidle" });
  record("搜索超页回到有效页", (await page.locator(".landmark-card").count()) > 0, `cards=${await page.locator(".landmark-card").count()}`);

  // 对比度：详情页正文文字实测（WCAG 1.4.3）
  await page.goto(`${baseUrl}/landmarks/${landmarkId}`, { waitUntil: "networkidle" });
  const contrast = await contrastReport(page);
  record(
    "详情页正文对比度 ≥4.5:1",
    contrast.checked > 0 && contrast.offenders.length === 0,
    `checked=${contrast.checked} worst=${JSON.stringify(contrast.worst)}${contrast.offenders.length ? " 低于阈值: " + JSON.stringify(contrast.offenders) : ""}`,
  );

  // 键盘：Tab 进入页面后焦点环可见
  await page.goto(`${baseUrl}/`, { waitUntil: "networkidle" });
  await page.keyboard.press("Tab");
  const focusInfo = await page.evaluate(() => {
    const element = document.activeElement;
    const style = getComputedStyle(element);
    return {
      tag: element.tagName,
      text: (element.textContent || "").trim().slice(0, 16),
      outlineStyle: style.outlineStyle,
      outlineWidth: style.outlineWidth,
    };
  });
  record(
    "键盘 Tab 焦点环可见",
    focusInfo.outlineStyle !== "none" && parseFloat(focusInfo.outlineWidth) >= 2,
    JSON.stringify(focusInfo),
  );

  // 地图：输入搜索、清空、重置
  await page.goto(`${baseUrl}/maps/games`, { waitUntil: "networkidle" });
  await page.waitForSelector(".map-group");
  const totalGroups = await page.locator(".map-group").count();
  const beforeCount = await page.locator(".map-locate-count").textContent();
  await page.locator("#map-locate-search").fill("应县");
  await page.waitForTimeout(300);
  const filteredText = await page.locator(".map-locate-count").textContent();
  record("地图搜索更新数量", filteredText !== beforeCount, `${beforeCount} -> ${filteredText}`);
  await page.screenshot({ path: join(outDir, "desktop-map-filtered.png"), fullPage: true });

  await page.locator("#map-locate-search").fill("不存在的作品zzz");
  await page.waitForTimeout(300);
  record("地图无匹配给出提示", (await page.locator("#map-status").textContent())?.includes("没有匹配"));
  await page.locator("#map-locate-reset").click();
  await page.waitForTimeout(500);
  const afterReset = await page.locator(".map-locate-count").textContent();
  const visibleGroups = await page.locator(".map-group:visible").count();
  record(
    "地图重置恢复全部",
    visibleGroups === totalGroups && (await page.locator("#map-locate-search").inputValue()) === "",
    `groups ${visibleGroups}/${totalGroups}, ${afterReset}`,
  );

  const mapOverflow = await horizontalOverflow(page);
  record("桌面地图无横向溢出", mapOverflow.scrollWidth <= mapOverflow.innerWidth + 1, JSON.stringify(mapOverflow));
  await page.screenshot({ path: join(outDir, "desktop-map.png"), fullPage: true });
  await runAxe(page, "地图页");

  // ------------------------------------------------ 360 / 390 / 768 / 1440 视口
  for (const viewport of [
    { width: 360, height: 800, tag: "mobile-sm" },
    { width: 390, height: 844, tag: "mobile" },
    { width: 768, height: 1024, tag: "tablet" },
    { width: 1440, height: 900, tag: "desktop-wide" },
  ]) {
    const touchOptions = viewport.width <= 430
      ? {
          isMobile: true,
          hasTouch: true,
          deviceScaleFactor: 3,
          userAgent:
            "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
        }
      : {};
    const context = await browser.newContext({ viewport: { width: viewport.width, height: viewport.height }, ...touchOptions });
    const mobilePage = await context.newPage();
    attachDiagnostics(mobilePage, viewport.tag);

    for (const path of ["/", `/landmarks/${landmarkId}`, "/maps/games", "/search?q=应县"]) {
      await mobilePage.goto(`${baseUrl}${path}`, { waitUntil: "networkidle" });
      const overflow = await horizontalOverflow(mobilePage);
      record(
        `${viewport.tag} ${path} 无横向溢出`,
        overflow.scrollWidth <= overflow.innerWidth + 1,
        JSON.stringify(overflow),
      );
      if (path === "/" && viewport.width <= 430) {
        // WebKit(Windows) 不支持 hasTouch 仿真，只记录实测值，不据此判定失败
        const touchPoints = await mobilePage.evaluate(() => navigator.maxTouchPoints);
        record(
          viewport.tag + " 触屏仿真生效",
          engineName === "chromium" ? touchPoints > 0 : true,
          "engine=" + engineName + " maxTouchPoints=" + touchPoints,
        );
      }
      if (path === "/" && viewport.width === 390) {
        await runAxe(mobilePage, "手机首页");
      }
      if (path === "/") {
        const mobileContrast = await contrastReport(mobilePage);
        record(
          `${viewport.tag} 首页正文对比度 ≥4.5:1`,
          mobileContrast.checked > 0 && mobileContrast.offenders.length === 0,
          `checked=${mobileContrast.checked} worst=${JSON.stringify(mobileContrast.worst)}${mobileContrast.offenders.length ? " 低于阈值: " + JSON.stringify(mobileContrast.offenders) : ""}`,
        );
      }
    }
    await mobilePage.goto(`${baseUrl}/landmarks/${landmarkId}`, { waitUntil: "networkidle" });
    const detailTargets = await targetReport(mobilePage, [".detail-actions a", ".album-button", ".album-manage-link"]);
    record(
      `${viewport.tag} 详情主操作与相册控件 ≥44×44`,
      detailTargets.filter((item) => item.count > 0 && (item.minHeight < 44 || item.minWidth < 44)).length === 0,
      JSON.stringify(detailTargets),
    );

    await mobilePage.screenshot({ path: join(outDir, `${viewport.tag}-home.png`), fullPage: true });
    await mobilePage.goto(`${baseUrl}/maps/games`, { waitUntil: "networkidle" });
    const targets = await targetReport(mobilePage, [
      ".site-nav a",
      "#map-locate-search",
      "#map-locate-reset",
      "#map-reset",
      ".map-locate-list button",
    ]);
    const tooSmall = targets.filter((item) => item.count > 0 && (item.minHeight < 44 || item.minWidth < 44));
    record(
      `${viewport.tag} 主要触控目标 ≥44×44`,
      tooSmall.length === 0,
      JSON.stringify(targets),
    );
    await mobilePage.screenshot({ path: join(outDir, `${viewport.tag}-map.png`), fullPage: true });
    await mobilePage.goto(`${baseUrl}/search?q=测试地标`, { waitUntil: "networkidle" });
    const pagerTargets = await targetReport(mobilePage, [".pagination .page-link"]);
    record(
      `${viewport.tag} 分页控件 ≥44 高`,
      pagerTargets.every((item) => item.count === 0 || item.minHeight >= 44),
      JSON.stringify(pagerTargets),
    );
    await context.close();
  }

  await desktop.close();
} catch (error) {
  record("浏览器流程异常中断", false, error.message);
} finally {
  await browser.close();
}

const appErrors = consoleErrors.filter((entry) => !/favicon|tile|openstreetmap|tileerror/i.test(entry.message));
record("控制台无应用异常", appErrors.length === 0, appErrors.map((entry) => entry.message).slice(0, 3).join(" | "));

const report = {
  engine: engineName,
  base_url: baseUrl,
  generated_at: new Date().toISOString(),
  passed: results.filter((item) => item.ok).length,
  failed: failureCount,
  results,
  console_errors: consoleErrors,
  axe: axeResults,
};
writeFileSync(join(outDir, "browser-smoke.json"), JSON.stringify(report, null, 2), "utf-8");
console.log(`\n${report.passed} passed, ${report.failed} failed`);
process.exit(report.failed === 0 ? 0 : 1);
