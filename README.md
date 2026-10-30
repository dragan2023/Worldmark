# 🧭 Worldmark · IP 地标旅游应用

> 以文学、游戏、影视剧作品中的地标为线索，发现并规划一场「作品照进现实」的旅行。

![Version](https://img.shields.io/badge/version-1.0.0-2b6cb0)
![Python](https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)
![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-2.0-d71f00)
![License](https://img.shields.io/badge/license-%E7%A7%81%E6%9C%89%E4%BB%93%E5%BA%93-2b6cb0)

---

## 项目初衷

本项目源于对**文学、游戏、影视剧地标旅游**的兴趣：当我们在小说里读到一座城、在游戏里走过一片地图、在荧幕上看到一处取景地时，往往会想——**这些地方真的存在吗？我可以去那里走一走吗？**

IP 地标旅游应用把这份好奇心变成可检索、可规划的工具，让每一次旅行都能带上作品的故事。

**名字由来**：Worldmark = **World**（作品里的世界）+ **Mark**（地标 / 标记），与 *bookmark*（书签）同构——为热爱作品的世界，在真实地图上做一个书签。

## ✨ 特性

- 🗂️ **三类 IP 地标目录**：文学 `/literature`、游戏 `/games`、影视剧 `/screen`，统一检索与详情页
- 🧾 **候选发现与人工审核**：搜索候选不自动发布，经审核后才会公开，保证数据可靠
- 🗺️ **轻量级地图与线路**：静态点位展示与已发布路线，基于 OpenStreetMap 瓦片
- 🧳 **个性化行程规划**：一级用户可用“基础规划”（无需任何外部密钥）生成行程，可选外部酒旅增强；支持编辑名称/时间/备注与 HTML / DOCX / XLSX 导出
- 🔍 **统一目录 API**：按作品、国家/地区、省市筛选；目录在线导出于 2026-10 下线（仅保留行程导出）
- 🤖 **一键入库 AI Agent**：输入「作品名 + 地标名」，AI 自动解析意图、联网核实、生成三段式简介并补全坐标，一键生成候选条目（`/intake`）
- 🖼️ **地标相册管理**：多图上传组件支持点击放大、右上角 × 移除与信息编辑；内置 AI 找图（LLM 生成检索词 + Wikimedia Commons 免费授权图库检索下载）产出的候选图片落在同一组件中，Commons 图自动带许可与作者署名，人工确认后提交才会对外展示
- 🔑 **API 配置页**：内置美团酒旅、高德、LLM（OpenAI 兼容）等客户端的状态总览，支持在页面填 Key 快捷写入本机 `.env`，并提供各平台申请入口（`/settings/api`）
- 🤝 **共创闭环**：登录会员在 `/intake`（导航「参与共创」）用一句自然语言提交候选地标，在 `/contributions`「我的贡献」查看审核状态与反馈；发布后展示提交者署名并自动升级账号

## 🚀 快速开始

### 环境要求

- Python 3.13
- PostgreSQL（本地数据库）
- Node.js（含 `npx`，可选：仅使用美团酒旅 Token 的行程价格参考时需要）

> 本项目使用项目根目录的虚拟环境，请勿使用系统 Python 安装或运行项目依赖。

### 安装与运行

1. 创建项目虚拟环境（系统 Python 只用来创建 venv，不安装任何项目依赖）：

   ```powershell
   py -3.13 -m venv .venv
   ```

2. 复制 `.env.example` 为本机 `.env`，填写数据库连接和随机的 `APP_SECRET_KEY`。地图与旅游计划所需 API Key 的申请与配置见下方「配置 API Key」小节；请勿把真实密钥提交到仓库：

   ```powershell
   Copy-Item .env.example .env
   ```

   `APP_SECRET_KEY` 同时用于签发登录令牌和加密用户自配密钥：生产环境（`APP_ENV=production`）若留空、使用示例值或长度不足 32 位，应用会直接拒绝启动；且**不要事后更换**，否则已保存的用户密钥将无法解密。

3. 安装依赖（`requirements.txt` 已包含运行、迁移与测试所需的全部直接依赖：`cryptography` 用于密钥加密，`Pillow` 用于上传图片真实校验）：

   ```powershell
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
   ```

4. 创建 / 升级数据库（空库与旧库都走同一套 Alembic 迁移）：

   ```powershell
   .\.venv\Scripts\python.exe -m alembic upgrade head
   ```

   迁移覆盖账号体系（用户名、角色、状态、最后登录）、地标软删字段与用户密钥表。SQLite 与 PostgreSQL 均实测可从空库一次迁移到 head（PostgreSQL 16 实测 0001→0008）。旧库结构不确定时先跑只读差异报告，不要删库：

   ```powershell
   .\.venv\Scripts\python.exe scripts\check_schema_drift.py
   ```

5. 启动开发服务：

   ```powershell
   .\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
   ```

6. 访问 <http://127.0.0.1:8000>。健康检查分两级：`/health/live` 只表示进程存活；`/health/ready` 会检查数据库连接与迁移版本是否已到 head，未迁移时返回 503。

> **外部调用排障**：若系统设了 `http_proxy`/`https_proxy` 但代理进程没启动，高德/DeepSeek 等会报连接被拒；请启动代理或清掉这两个变量。`NO_PROXY` 里的 `[::1]` 会被 httpx 误解析成非法端口，应用已在导入配置时自动去掉方括号（`app/core/http_env.py`）。

### 使用示例

统一目录 API 支持按作品与地区筛选，例如：

```text
GET /api/v1/landmarks?ip_type=game&work=黑神话悟空&country=CN&province=山西省&city=大同市
```

当前**没有**在线目录导出路由：`/api/v1/exports/landmarks.csv|xlsx` 已下线，旧的 `LandmarkExportService` 也一并移除（表格导出只保留在“我的行程”的 HTML / DOCX / XLSX 三种格式中）。如需离线取数，请使用迁移后的数据库或有权限的管理接口。

### 参与共创（AI 生成候选条目）

打开 `/intake`「参与共创」页，用一句自然语言描述「作品 + 地标」并提交，例如：

```text
《黑神话：悟空》 小西天
金庸《射雕英雄传》 华山
```

内置 AI Agent 会依次完成：解析输入 → DeepSeek 网页检索核实现实资料 → 生成三段式简介与结构化字段 → 高德/Nominatim 地理编码补全坐标 → 以**候选（candidate）状态入库**。页面会展示生成结果、参考来源与需要人工复核的提示；候选条目不会直接公开，需管理员审核发布后才会出现在目录中。

- 需要 `DEEPSEEK_API_KEY`（或任意 OpenAI 兼容 LLM Key）才能运行；未配置时页面会引导前往「API 配置」页。
- `AMAP_WEB_SERVICE_API_KEY` 可选：未配置时将跳过坐标补全并给出警告，绝不编造坐标。联网核实与 LLM 共用 `DEEPSEEK_API_KEY`（`/v1/tools/search`），未配置时同样跳过并提示。
- 相同「作品 + 地标名 + 地址」的组合会被去重拦截（HTTP 409）。

对应的 API 为 `POST /api/v1/agent/landmarks/intake`，请求体 `{"input": "作品名 地标名"}`，需登录会员身份。

### 地标相册：上传、AI 找图与提交

地标详情页的「地标相册」区块提供「管理相册」入口（也可直接访问 `/landmarks/{id}/album/edit`，候选地标同样可用）：

1. **上传图片**：多选上传 JPG / PNG / WebP / AVIF（单张 ≤ 8MB，单次 ≤ 12 张），图片先进入本机暂存区 `uploads/landmark_albums/`；
2. **AI 找图**：LLM 生成 Commons 友好的短检索词（中文原名 + 地名罗马化 + 区县消歧）→ Wikimedia Commons 图片检索 → LLM 按标题与来源剔除同名异地干扰 → 自动下载至多 6 张候选图。Commons 图自带自由授权（如 CC BY-SA）与作者署名，下载即自动填好许可与来源链接；与上传图片落在同一组件中，不满意的直接点 × 移除；
3. **编辑与确认**：点击小图放大预览，并编辑图片说明（必填）、图注、署名、版权与来源链接；点图片右上角 × 移除（已发布图片标记移除，提交后移入 `_trash` 回收站）；
4. **提交相册**：确认后一键落库——暂存文件移入正式相册目录并原子化更新 `manifest.json`，立即在详情页展示。

> AI 找图的图片来源为 Wikimedia Commons（免 Key、自由授权），`DEEPSEEK_API_KEY` 用于检索词生成与候选去歧义排序（未配置时直接用地标名检索）；「参与共创」的联网核实同样使用 `DEEPSEEK_API_KEY`（`/v1/tools/search`），网页正文通过 `/v1/tools/fetch` 抓取。上传图片默认带「自行确认版权」标记，展示即代表维护者确认可用。

### 行程规划模式

| 模式 | 入口 | 是否需要密钥 | 结果标记 |
| --- | --- | --- | --- |
| 基础规划（默认） | `POST /api/v1/itineraries`，页面默认勾选状态 | 不需要 | `generation_mode=basic` |
| 模型生成 | 同上；配置了 DeepSeek 时自动使用 | `DEEPSEEK_API_KEY`（或自配） | `generation_mode=llm` |
| 外部增强 | 页面勾选「外部行程增强」→ `POST /api/v1/itineraries/finalize` | 美团酒旅 Token（+ 高德可选） | `generation_mode=enhanced` |

外部增强失败时接口返回结构化错误（`code=enhancement_unavailable`、`reason`、`config_url`、`fallback`），并提示改用基础规划；不会把失败包装成已确认行程，也不会悄悄回落到系统密钥。

## 🔑 配置 API Key（地图与旅游计划）

地图展示与个性化旅游计划会调用外部地图 / AI / 旅游服务。**不配置任何 Key 也能正常浏览目录与导出数据**，但以下功能需要对应的 Key 才会启用完整能力：

> **快捷方式**：启动应用后打开 [`/settings/api`](http://127.0.0.1:8000/settings/api)「API 配置」页，可以在这里查看每个内置客户端（LLM / 高德 / 美团 / 地图瓦片）的配置状态与掩码，直接填入 Key 保存到本机 `.env`（生产环境 `APP_ENV=production` 时网页写入会被禁用），也可以点「测试连通」即时验证，各客户端均附官方申请链接。下文为手工配置方式。

### 地图功能

| 配置项 | 作用 | 是否需要 | 申请 / 文档链接 |
| --- | --- | --- | --- |
| `MAP_TILE_URL` | 地图瓦片地址（默认已填 OpenStreetMap，可换成高德或其他合规瓦片服务） | 可选（默认可用） | — |
| `AMAP_WEB_SERVICE_API_KEY` | 高德 Web 服务 Key：地址地理编码、酒店坐标、步行距离动线优化 | 建议配置 | [高德开放平台 · 创建应用与 Key](https://console.amap.com/dev/key/app)（[Web 服务开发文档](https://lbs.amap.com/api/webservice/create-project-and-key)） |

### 旅游计划功能

| 配置项 | 作用 | 是否需要 | 申请 / 文档链接 |
| --- | --- | --- | --- |
| `DEEPSEEK_API_KEY` | **LLM API Key**（OpenAI 兼容接口）：启用 AI 行程生成，自动安排地标顺序与日程；不限定 DeepSeek，任何 OpenAI 兼容服务商均可；未配置时回退到确定性本地生成器。同一 Key 还用于联网检索（`/v1/tools/search`）与网页抓取（`/v1/tools/fetch`） | 建议配置 | [DeepSeek 开放平台 · API Keys](https://platform.deepseek.com/api_keys)（示例；其他厂商以各自开放平台为准） |
| `MEITUAN_HT_TOKEN` | 美团酒旅官方 Skill Token：生成行程草案，提供住宿 / 交通 / 门票价格参考 | 可选 | [美团开发者中心 · 获取 Token](https://developer.meituan.com/zh/v2/dev/token) |
| `AMAP_WEB_SERVICE_API_KEY` | 同地图功能，用于行程动线优化 | 建议配置 | [高德开放平台](https://console.amap.com/dev/key/app) |

> **LLM 说明**：系统通过 OpenAI 兼容的 `/chat/completions` 接口调用大模型，只需一个支持 OpenAI 格式的 LLM API Key。默认使用 DeepSeek；若使用其他服务商，把对应 Key 填入 `DEEPSEEK_API_KEY`，并在 `DEEPSEEK_BASE_URL` 填其接口地址、`DEEPSEEK_MODEL` 填其模型名即可。

> **美团酒旅 Token 说明**：把 Token 填到项目根目录 `.env` 的 `MEITUAN_HT_TOKEN=`（旧的 `MEITUAN_TRAVEL_TOKEN` 别名仍兼容）。Token 在[美团开发者中心](https://developer.meituan.com/zh/v2/dev/token)完成个人实名认证后获取。应用用固定版本 `npx @meituan-travel/ht-ai@0.0.6 query` 运行美团酒旅官方 Skill（不使用 `@latest`，升级需人工验证后修改常量或设置 `MEITUAN_SKILL_PACKAGE`）；未配置 Token 或本机没有 Node.js/npx 时，行程中的酒店 / 交通 / 门票价格参考会自动跳过，其他功能不受影响。

> 提示：`MAP_TILE_URL` 未配置时地图页会提示「地图瓦片服务未配置」。默认 OpenStreetMap 瓦片仅限用户主动浏览，禁止预抓取或离线下载；生产上线前请根据访问量改用符合业务规模与许可条件的地图服务，并保留可见署名。

### 配置步骤

1. 复制 `.env.example` 为 `.env`（若已存在则直接编辑）：

   ```powershell
   Copy-Item .env.example .env
   ```

2. 按上方表格把申请到的 Key 填入对应配置项，例如：

   ```dotenv
   AMAP_WEB_SERVICE_API_KEY=你的高德Web服务Key
   DEEPSEEK_API_KEY=你的LLM API Key（不限于 DeepSeek，OpenAI 兼容接口即可）
   MEITUAN_HT_TOKEN=你的美团Token
   ```

3. 重启开发服务使配置生效：

   ```powershell
   .\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
   ```

> ⚠️ `.env` 已被 git 忽略，请勿把真实 Key 提交到仓库或公开环境；泄露后请及时到对应平台吊销并重新申请。

## 🤝 如何参与共创

欢迎为 Worldmark 贡献新的文学 / 游戏 / 影视地标条目。共创已改为**应用内一键入库**：不需要 Fork 仓库、不需要手写 CSV、不需要开 Pull Request——注册登录后，用一句自然语言描述即可。

1. **注册 / 登录**（[注册页面](/register)）：注册即为二级用户，已具备提交候选地标的权限。
2. **打开 [`/intake`「参与共创」页](/intake)**：用一句自然语言描述「作品 + 地标」，例如「情书 小樽运河」。
3. **AI 自动补全**：解析作品与地标 → 联网核实现实资料 → 生成三段式原创简介与结构化字段 → 地理编码补全坐标，最终以**候选（candidate）状态**入库，不会直接公开。
4. **人工审核后发布**：管理员在 `/admin` 复核并发布为 `verified` 后，条目才出现在目录、导出与地图中，详情页展示提交者署名。
5. **贡献者自动升级**：你提交的条目被发布后，账号自动升为一级用户（解锁个性化行程），只升不降、幂等。
6. **查看审核反馈**：在 [`/contributions`「我的贡献」页](/contributions) 可以看到自己每条候选的当前状态（待审核 / 已核验待发布 / 已发布 / 已拒绝）、审核意见与更新时间；修改内容或相册后会**暂时下架并重新审核**，保存不代表立即公开。

> 候选条目不会出现在公开目录、导出或地图中；相同「作品 + 地标名 + 地址」的组合会被去重拦截；条目必须提供可访问来源与三段式原创简介。

规范与字段要求见 [`docs/共创贡献规范.md`](docs/共创贡献规范.md) 与 [`docs/数据采集规范.md`](docs/数据采集规范.md)；LLM / 联网核实 / 坐标补全的 Key 配置见上文「一键入库（AI 生成候选条目）」小节。

## 👥 用户系统（注册 / 角色 / 密钥隔离）

应用内置三级用户体系（见 docs/用户系统开发计划.md）：

| 角色 | 权限 |
| --- | --- |
| **管理员**（admin） | 全部功能 + 用户管理（/admin/users）+ 条目审核/修改/下架/删除 + 系统密钥配置（/settings/api，未自配时可回落系统密钥） |
| **一级用户**（level1） | 二级权限 + **个性化行程**（基础规划 / 可选外部增强 / 三种格式导出） |
| **二级用户**（level2） | 浏览地图与目录 + 提交候选地标 + 相册管理 + 我的贡献记录 |

- 注册即成为二级用户（[注册页面](/register)），**登录标识为自定义用户名**（3-32 位英文/数字/下划线，邮箱仅作资料与找回联系用）；贡献的地标被管理员**发布后自动升为一级用户**（只升不降，幂等）。
- 登录采用 JWT（HttpOnly Cookie，8 小时）+ Bearer 双通道；封禁即时生效，已签发的 token 也会被拒绝。
- 登录接口内置内存级限速：同一 IP 15 分钟内连续失败 8 次将返回 429。

### 🔐 按用户隔离密钥

需要调用第三方付费服务（DeepSeek / 高德 / 美团）的功能遵循 **"自己的密钥自己配"**：

1. 登录后进入 **[个人密钥页](/account/api-keys)**，粘贴并保存你的密钥（可选保存前连通性验证）。
2. 密钥经 Fernet（AES-CBC+HMAC，由 APP_SECRET_KEY 派生）静态加密存储，页面与接口**永不回传明文**。
3. 未自配密钥的普通用户调用相应功能会收到 403 user_key_required 提示（含 config_url 指向个人密钥页），**不会消耗系统密钥额度**。
4. 管理员未自配时自动回落系统密钥；系统级密钥配置页（/settings/api）仅管理员可见。
5. 免密钥功能：浏览地图、OSM 瓦片、AI 找图（Wikimedia Commons）。

管理员可在 /admin/users 调整用户角色、封禁/解封账号（软删，保留贡献归属与审计）；条目支持修改、下架与软删除（可恢复）。

### ✏️ 地标内容与相册的修改规则

- **贡献者**可以修改自己提交的地标内容（名称/简介/交通）并管理其相册；**每一次修改都会使地标回到「待审核」并暂时下架**，需管理员重新审核通过后再次上架。
- **管理员**可以修改任意地标内容与相册，**即时生效**，不进入审核流程。
- 其他用户无权修改非本人提交的地标（403）。

## 🧪 测试

```powershell
# 使用独立临时目录，避免旧测试缓存目录的权限问题
.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp=.pytest-run
```

测试使用临时 SQLite 数据库，不连接也不修改正式库；外部服务统一用替身，测试前会清空第三方凭据环境变量。迁移测试直接运行 Alembic，不用 `create_all` 绕过被测迁移。

测试分两层，证据等级不同：

- `tests/e2e/` 是**进程内 FastAPI `TestClient`** 的流程回归，不启动真实浏览器，也不验证 CSS/JS 与视口行为（见 `tests/e2e/README.md`）。
- `tests/browser/smoke.mjs` 是**真实 Chromium** 冒烟，由 `scripts/run_browser_smoke.py` 拉起隔离服务与临时数据库后驱动：覆盖 360 / 390 / 768 / 1280 / 1440 视口横向溢出、地图搜索与重置、登录返回、基础规划生成、编辑保存与三格式导出、我的贡献记录，以及对比度和触控尺寸实测。

```powershell
.\.venv\Scripts\python.exe scripts\run_browser_smoke.py --out 测试证据\项目改进实施20261022\browser
```

可叠加两项增强（都需要先装测试侧依赖，不进入运行环境）：

```powershell
# 1) 无障碍审计：axe-core 注入后对首页/详情/行程表单/我的贡献/地图/手机首页跑 WCAG 2.0/2.1 A+AA
$env:AXE_MODULE = "C:/Users/Administrator/.workbuddy/binaries/node/workspace/node_modules/axe-core/axe.min.js"

# 2) 换引擎：WebKit（Safari 内核；手机视口会同时开启 isMobile + hasTouch + iPhone UA）
$env:BROWSER_ENGINE = "webkit"

..venv\Scripts\python.exe scripts\run_browser_smoke.py --out 测试证据\项目改进实施20261022\browser-webkit
```

> axe 覆盖的是可访问名称、角色、标签、对比度等**机器可判定**项，不能替代真实读屏（NVDA/VoiceOver）验证；WebKit-on-Windows 也不支持触摸仿真，手机结论来自视口与触屏参数仿真，并非物理设备。

发布已审核地标前，可运行数据质量检查：

```powershell
.\.venv\Scripts\python.exe -m app.scripts.check_data_quality
```

## 🛠️ 技术栈

| 分类 | 技术 |
| --- | --- |
| Web 框架 | FastAPI + Uvicorn |
| ORM / 迁移 | SQLAlchemy 2.x + Alembic |
| 数据库 | PostgreSQL（本地测试与默认配置用 SQLite） |
| 前端 | Jinja2 模板 + 原生 CSS/JS + Leaflet |
| 认证 | JWT（HS256）+ 标准库 PBKDF2-SHA256 口令散列；用户密钥用 Fernet 静态加密 |
| 集成 | httpx（DeepSeek 检索与 LLM、高德 Web Service、美团酒旅 Skill） |
| 导出 | openpyxl（XLSX）、python-docx（DOCX） |

## 📁 项目结构

```text
├── app/                  # 应用主代码
│   ├── api/              # 对外 API 路由
│   ├── core/             # 配置与认证
│   ├── db/               # 数据库会话
│   ├── integrations/     # 外部服务集成（搜索、LLM 默认 DeepSeek、高德、美团）
│   ├── models/           # SQLAlchemy 数据模型
│   ├── services/         # 业务逻辑（目录、审核、行程、地图数据等）
│   ├── static/           # CSS / JS / 静态资源
│   ├── templates/        # Jinja2 页面模板
│   └── web/              # Web 页面路由
├── alembic/              # 数据库迁移脚本
├── data/                 # 种子数据、模板与共创图片
├── docs/                 # 项目文档与实施计划
├── scripts/              # 辅助脚本
├── tests/                # 自动化测试
├── alembic.ini
├── requirements.txt
└── 启动开发服务.bat
```

## 📚 文档

- [共创贡献规范](docs/共创贡献规范.md)
- [数据采集规范](docs/数据采集规范.md)
- [来源分级与审核准则](docs/来源分级与审核准则.md)
- [隐私与数据保留说明](docs/隐私与数据保留说明.md)

## 📝 范围与说明

- 当前版本没有真实支付、网页爬虫；候选发现通过受管理员令牌保护的 DeepSeek 检索 API 进行，搜索结果不会自动发布。行程的“基础规划”由确定性本地生成器完成，不需要任何外部密钥；只有勾选“外部行程增强”才调用美团酒旅 / 高德，失败时返回结构化 `enhancement_unavailable`，不会伪装成已确认行程。
- 目录在线导出已于 2026-10 下线：没有 `/api/v1/exports/landmarks.csv|xlsx` 路由，`LandmarkExportService` 也已移除。页面与 API 仍提供作品名称、地标名称、国家/地区、详细地址、地标简介和信息更新时间，但不输出交通文字、坐标、地图瓦片、审核记录或未发布候选。
- 地标相册只加载 `data/contributions/landmark_albums/` 中已登记许可信息的本地图片；暂存图与未公开地标的图片都走鉴权路由，匿名或非贡献者无法直接读取。
- 公开浏览不要求登录：目录、详情、搜索、静态点位 API、`/maps/{module}` 地图页与已发布路线对外开放。个性化行程属于一级（level1）能力：匿名访问行程页面跳转登录并带回原任务地址，二级用户得到明确的能力说明。付费会员层（FREE/LITE/PREMIUM）保留，但不参与上述权限判定。
- 共创采用应用内一键入库：登录会员在 `/intake` 用自然语言提交候选地标，AI 负责解析、联网核实、生成三段式简介并补全坐标，条目以 candidate 状态入库；经管理员审核发布后才公开，并向提交者署名、自动升级账号。仓库不再接收共创 PR，也不再有 PR 审核机器人。
- 一级用户（level1）与管理员可通过 `/itineraries` 创建、查看、编辑、删除个性化行程草案，并导出 HTML、DOCX 和 XLSX。默认使用“基础规划”：不依赖任何外部服务，按已发布 IP 地标生成可编辑日程；勾选“外部行程增强”才调用美团酒旅 `@meituan-travel/ht-ai@0.0.6`（版本固定，不在请求现场安装）与高德 Web Service（酒店地址地理编码、步行距离优化当天动线）。编辑时提交 `expected_version`，旧版本编辑返回 409 而不是静默覆盖。酒店、交通、门票和餐饮的官方建议须由用户自行确认，系统不会自动下单或写入未确认价格。
- 静态地图只做地标分布与路线顺序参考，不提供实时导航。默认 `MAP_TILE_URL` 使用 OpenStreetMap 标准瓦片 URL：仅限用户主动浏览，禁止预抓取、离线下载或自行抓取瓦片；生产上线前应根据访问量改用符合业务规模与许可条件的地图服务，并保留可见署名和有效 Referer。

## 📦 版本记录

| 版本 | 日期 | 说明 |
| --- | --- | --- |
| v1.1.1 | 2026-10-22 | 授权后执行正式库与正式相册迁移（行数/图片零丢失）；PostgreSQL 16 实测并修复 `alembic_version` 列宽导致的迁移失败；修复 `NO_PROXY` 含 `[::1]` 时 httpx 报 InvalidURL（影响高德/DeepSeek）；页脚链接补非颜色区分（WCAG 1.4.1）；新增 axe 无障碍审计、WebKit 与 iPhone 仿真浏览器回归、多进程相册并发验证 |
| v1.1.0 | 2026-10-22 | 改进轮：Alembic `0008` 补齐账号/软删/用户密钥表；页面与 API 权限统一到 level1；公开条件集中为单一判定；相册改为按 `landmark:<id>` 绑定并做真实图片解码校验；行程拆分为基础规划与外部增强并加编辑版本冲突；新增公共页面骨架、地图搜索修复与我的贡献记录；新增 `/health/ready`、请求标识与真实浏览器回归 |
| v1.0.0 | 2026-08-17 | 初始版本：基础框架、候选数据审核流程、三类地标目录、免费导出、会员地图与线路、个性化行程 |

## 📄 License

项目仓库当前为**公开仓库**（<https://github.com/dragan2023/Worldmark>），可公开浏览；仓库暂未附加开源许可证，默认保留所有权利，具体授权条款以仓库声明为准。共创者提交的条目按 [共创贡献规范](docs/共创贡献规范.md) 审核、署名与发布。

