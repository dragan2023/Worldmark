# 🧭 Worldmark · IP 地标旅游应用

> 以文学、游戏、影视剧作品中的地标为线索，发现并规划一场「作品照进现实」的旅行。

![Version](https://img.shields.io/badge/version-1.0.0-2b6cb0)
![Python](https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)
![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-2.0-d71f00)
![License](https://img.shields.io/badge/license-%E5%85%AC%E5%BC%80%E4%BB%93%E5%BA%93-2b6cb0)

---

## 项目初衷

本项目源于对**文学、游戏、影视剧地标旅游**的兴趣：当我们在小说里读到一座城、在游戏里走过一片地图、在荧幕上看到一处取景地时，往往会想——**这些地方真的存在吗？我可以去那里走一走吗？**

IP 地标旅游应用把这份好奇心变成可检索、可规划的工具，让每一次旅行都能带上作品的故事。

**名字由来**：Worldmark = **World**（作品里的世界）+ **Mark**（地标 / 标记），与 *bookmark*（书签）同构——为热爱作品的世界，在真实地图上做一个书签。

## ✨ 特性

- 🗂️ **三类 IP 地标目录**：文学 `/literature`、游戏 `/games`、影视剧 `/screen`，统一检索与详情页
- 🧾 **候选发现与人工审核**：搜索候选不自动发布，经审核后才会公开，保证数据可靠
- 🗺️ **轻量级地图与线路**：静态点位展示与已发布路线，基于 OpenStreetMap 瓦片
- 🧳 **个性化行程规划**：所有用户均可创建行程草案，并导出 HTML / DOCX / XLSX
- 🔍 **统一目录 API 与免费导出**：按作品、国家/地区、省市筛选，CSV / XLSX 一键导出
- 🤝 **共创贡献**：任何人可 Fork 仓库并以 PR 提交地标条目（Harness 共创），审核发布后展示共创者署名

## 🚀 快速开始

### 环境要求

- Python 3.13
- PostgreSQL（本地数据库）
- Node.js（含 `npx`，可选：仅使用美团酒旅 Token 的行程价格参考时需要）

> 本项目使用项目根目录的虚拟环境，请勿使用系统 Python 安装或运行项目依赖。

### 安装与运行

1. 复制 `.env.example` 为本机 `.env`，填写本地 PostgreSQL 连接和随机的 `APP_SECRET_KEY`。地图与旅游计划所需 API Key 的申请与配置见下方「配置 API Key」小节；请勿把真实密钥提交到仓库：

   ```powershell
   Copy-Item .env.example .env
   ```

2. 安装依赖：

   ```powershell
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
   ```

3. 创建 / 升级数据库：

   ```powershell
   .\.venv\Scripts\python.exe -m alembic upgrade head
   ```

4. 启动开发服务：

   ```powershell
   .\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
   ```

5. 访问 <http://127.0.0.1:8000>，健康检查为 <http://127.0.0.1:8000/health/live>。

### 使用示例

统一目录 API 支持按作品与地区筛选，例如：

```text
GET /api/v1/landmarks?ip_type=game&work=黑神话悟空&country=CN&province=山西省&city=大同市
```

当前筛选结果可从以下接口免费导出（最多 1,000 条，只包含已审核、已发布的地标）：

```text
GET /api/v1/exports/landmarks.csv
GET /api/v1/exports/landmarks.xlsx
```

## 🔑 配置 API Key（地图与旅游计划）

地图展示与个性化旅游计划会调用外部地图 / AI / 旅游服务。**不配置任何 Key 也能正常浏览目录与导出数据**，但以下功能需要对应的 Key 才会启用完整能力：

### 地图功能

| 配置项 | 作用 | 是否需要 | 申请 / 文档链接 |
| --- | --- | --- | --- |
| `MAP_TILE_URL` | 地图瓦片地址（默认已填 OpenStreetMap，可换成高德或其他合规瓦片服务） | 可选（默认可用） | — |
| `AMAP_WEB_SERVICE_API_KEY` | 高德 Web 服务 Key：地址地理编码、酒店坐标、步行距离动线优化 | 建议配置 | [高德开放平台 · 创建应用与 Key](https://console.amap.com/dev/key/app)（[Web 服务开发文档](https://lbs.amap.com/api/webservice/create-project-and-key)） |

### 旅游计划功能

| 配置项 | 作用 | 是否需要 | 申请 / 文档链接 |
| --- | --- | --- | --- |
| `DEEPSEEK_API_KEY` | **LLM API Key**（OpenAI 兼容接口）：启用 AI 行程生成，自动安排地标顺序与日程；不限定 DeepSeek，任何 OpenAI 兼容服务商均可；未配置时回退到确定性本地生成器 | 建议配置 | [DeepSeek 开放平台 · API Keys](https://platform.deepseek.com/api_keys)（示例；其他厂商以各自开放平台为准） |
| `MEITUAN_HT_TOKEN` | 美团酒旅官方 Skill Token：生成行程草案，提供住宿 / 交通 / 门票价格参考 | 可选 | [美团开发者中心 · 获取 Token](https://developer.meituan.com/zh/v2/dev/token) |
| `AMAP_WEB_SERVICE_API_KEY` | 同地图功能，用于行程动线优化 | 建议配置 | [高德开放平台](https://console.amap.com/dev/key/app) |
| `BOCHA_API_KEY` | 博查 AI 搜索 Key：候选地标发现与行程资料检索 | 可选 | [博查 AI 开放平台 · API Keys](https://open.bochaai.com/api-keys) |

> **LLM 说明**：系统通过 OpenAI 兼容的 `/chat/completions` 接口调用大模型，只需一个支持 OpenAI 格式的 LLM API Key。默认使用 DeepSeek；若使用其他服务商，把对应 Key 填入 `DEEPSEEK_API_KEY`，并在 `DEEPSEEK_BASE_URL` 填其接口地址、`DEEPSEEK_MODEL` 填其模型名即可。

> **美团酒旅 Token 说明**：把 Token 填到项目根目录 `.env` 的 `MEITUAN_HT_TOKEN=`（旧的 `MEITUAN_TRAVEL_TOKEN` 别名仍兼容）。Token 在[美团开发者中心](https://developer.meituan.com/zh/v2/dev/token)完成个人实名认证后获取。首次调用时应用会用 `npx @meituan-travel/ht-ai@latest query` 运行美团酒旅官方 Skill；未配置 Token 或本机没有 Node.js/npx 时，行程中的酒店 / 交通 / 门票价格参考会自动跳过，其他功能不受影响。

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


欢迎为 Worldmark 贡献新的文学 / 游戏 / 影视地标条目。**项目仓库已公开**，任何人都可以参与。共创采用 **Harness PR 共创**（一条地标 = 一个 CSV 文件 + PR 审核机器人）：

1. **Fork 本仓库**（仓库主页右上角 Fork 按钮），得到你自己的副本（`<你的用户名>/Worldmark`），克隆到本地。
2. 使用主流 AI 智能体工具（Codex、Claude Code、WorkBuddy、Qoder 等）打开项目目录，复制 [`docs/共创提示词包/01_共创条目添加提示词.md`](docs/共创提示词包/01_共创条目添加提示词.md) 中的提示词并执行，工具会自动联网核实、生成条目文件并完成本地校验。
3. 把新增的条目文件（仅 `data/contributions/entries/<ip_type>/<slug>.csv`）推送并开 Pull Request。审核机器人会自动运行两个检查：
   - `文件封锁检查`：只允许新增条目文件，改动其他任何代码/配置文件都会拦截并留言；
   - `validate-contribution`：校验条目字段、三段式简介与重复性，通过后留言「校验通过，等待维护者人工确认」。
4. **main 分支受保护**：两个检查必须全部通过、且 PR 基于最新 main 才能合并。通过后由维护者人工确认合入，合入后条目进入种子数据，并以你的 **GitHub 用户名**署名。
5. 共创者名单在 [共创者名单页面](https://dragan2023.github.io/Worldmark/) 实时展示（网页由 GitHub Pages 托管，每次名单更新后自动发布；数据源为 [contributors.json](data/contributions/contributors.json)）。

> 共创者只能新增自己的条目文件，不能修改、删除他人条目或任何既有代码；越界改动会被机器人拦截，无法合入。

详细说明见 [`docs/共创提示词包/00_使用说明.md`](docs/共创提示词包/00_使用说明.md) 与 [`docs/共创贡献规范.md`](docs/共创贡献规范.md)。

## 🧪 测试

```powershell
.\.venv\Scripts\python.exe -m pytest
```

测试使用临时 SQLite 数据库，不会连接或修改本地 PostgreSQL。

发布已审核地标前，可运行数据质量检查：

```powershell
.\.venv\Scripts\python.exe -m app.scripts.check_data_quality
```

## 🛠️ 技术栈

| 分类 | 技术 |
| --- | --- |
| Web 框架 | FastAPI + Uvicorn |
| ORM / 迁移 | SQLAlchemy 2.x + Alembic |
| 数据库 | PostgreSQL（测试用 SQLite） |
| 前端 | Jinja2 模板 + 原生 CSS/JS + Leaflet |
| 认证 | JWT + passlib/bcrypt |
| 集成 | httpx（博查搜索、LLM 默认 DeepSeek、高德 Web Service、美团酒旅 Skill） |
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

- [运行手册](docs/运行手册.md)
- [共创提示词包 · 使用说明](docs/共创提示词包/00_使用说明.md)
- [共创贡献规范](docs/共创贡献规范.md)
- [数据采集规范](docs/数据采集规范.md)
- [来源分级与审核准则](docs/来源分级与审核准则.md)
- [故障处理手册](docs/故障处理手册.md)
- [隐私与数据保留说明](docs/隐私与数据保留说明.md)
- [上线前数据检查清单](docs/上线前数据检查清单.md)

## 📝 范围与说明

- 当前版本没有真实支付、网页爬虫；候选发现通过受管理员令牌保护的博查搜索 API 进行，搜索结果不会自动发布。未配置 LLM API Key（`DEEPSEEK_API_KEY`，OpenAI 兼容接口，不限于 DeepSeek）时，行程生成回退到确定性本地生成器。
- 免费目录和 CSV/XLSX 导出统一提供作品名称、地标名称、国家/地区、详细地址、地标简介和信息更新时间；不会输出交通文字、坐标、地图瓦片、审核记录或未发布候选。
- 地标相册仅加载 `data/contributions/landmark_albums/` 中已登记许可信息的本地图片。
- 所有用户（无需登录）均可访问静态点位 API、`/maps/{module}` 地图页、已发布路线与个性化行程；系统不再按会员等级限制功能。
- 共创采用 Harness PR 工作流：任何人可 Fork 仓库、按提示词包生成条目 CSV 并提交 PR，经 GitHub 审核机器人校验与维护者人工合入后发布，并以 GitHub 用户名署名；条目不会直接公开。
- 所有用户均可通过 `/itineraries` 创建、查看、编辑、删除个性化行程草案，并导出 HTML、DOCX 和 XLSX。预览阶段使用美团酒旅官方 `@meituan-travel/ht-ai` Skill，本地服务始终校验已发布 IP 地标并生成可编辑的基础日程；配置 LLM API Key（`DEEPSEEK_API_KEY`，OpenAI 兼容接口，不限于 DeepSeek）时，可辅助安排本地 IP 地标顺序，调用失败时回退到确定性生成器；配置高德 Web Service 后，系统会自动使用酒店地址地理编码和步行距离优化当天动线。酒店、交通、门票和餐饮的官方建议须由用户自行确认，系统不会自动下单或写入未确认价格。
- 静态地图只做地标分布与路线顺序参考，不提供实时导航。默认 `MAP_TILE_URL` 使用 OpenStreetMap 标准瓦片 URL：仅限用户主动浏览，禁止预抓取、离线下载或自行抓取瓦片；生产上线前应根据访问量改用符合业务规模与许可条件的地图服务，并保留可见署名和有效 Referer。

## 📦 版本记录

| 版本 | 日期 | 说明 |
| --- | --- | --- |
| v1.0.0 | 2026-08-17 | 初始版本：基础框架、候选数据审核流程、三类地标目录、免费导出、会员地图与线路、个性化行程 |

## 📄 License

项目仓库当前为**公开仓库**，代码与数据对外可见。共创者提交的条目按 [共创贡献规范](docs/共创贡献规范.md) 署名与发布；具体授权条款以仓库声明为准。

