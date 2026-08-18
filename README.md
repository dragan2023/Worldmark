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
- 🗺️ **轻量级会员地图与线路**：静态点位展示与已发布路线，基于 OpenStreetMap 瓦片
- 🧳 **个性化行程规划**：`premium` 成员可创建行程草案，并导出 HTML / DOCX / XLSX
- 🔍 **统一目录 API 与免费导出**：按作品、国家/地区、省市筛选，CSV / XLSX 一键导出
- 🤝 **共创贡献**：任何人都可提交带署名的候选地标，审核发布后展示共创者署名

## 🚀 快速开始

### 环境要求

- Python 3.13
- PostgreSQL（本地数据库）

> 本项目使用项目根目录的虚拟环境，请勿使用系统 Python 安装或运行项目依赖。

### 安装与运行

1. 复制 `.env.example` 为本机 `.env`，填写本地 PostgreSQL 连接和随机的 `APP_SECRET_KEY`。不要填写或提交真实 API 密钥：

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

## 🤝 如何参与共创

欢迎为 Worldmark 贡献新的文学 / 游戏 / 影视地标条目。**项目仓库已公开**，任何人都可以参与。共创有**两种方式**：

### 方式一：网页提交（本地运行应用，单条）

网页提交表单是项目应用内置页面，需先在本地完成[「安装与运行」](#安装与运行)后访问 <http://127.0.0.1:8000/contribute>，填写作品、地标、简介与署名后提交，候选条目会进入人工审核；审核发布后展示署名。适合快速提交单条地标。

> 说明：GitHub 网页上无法直接打开该表单；在线参与共创请使用下方的方式二。

### 方式二：Harness PR 共创（推荐，批量可追溯）

「一条地标 = 一个 CSV 文件 + PR 审核机器人」：

1. **Fork 本仓库**（仓库主页右上角 Fork 按钮），得到你自己的副本（`<你的用户名>/Worldmark`），克隆到本地。
2. 使用主流 AI 智能体工具（Codex、Claude Code、WorkBuddy、Qoder 等）打开项目目录，复制 [`docs/共创提示词包/01_共创条目添加提示词.md`](docs/共创提示词包/01_共创条目添加提示词.md) 中的提示词并执行，工具会自动联网核实、生成条目文件并完成本地校验。
3. 把新增的条目文件（仅 `data/contributions/entries/<ip_type>/<slug>.csv`）推送并开 Pull Request。审核机器人会自动运行两个检查：
   - `文件封锁检查`：只允许新增条目文件，改动其他任何代码/配置文件都会拦截并留言；
   - `validate-contribution`：校验条目字段、三段式简介与重复性，通过后留言「校验通过，等待维护者人工确认」。
4. **main 分支受保护**：两个检查必须全部通过、且 PR 基于最新 main 才能合并。通过后由维护者人工确认合入，合入后条目进入种子数据，并以你的 **GitHub 用户名**署名。
5. 共创者名单在 [共创者名单](data/contributions/contributors.json) 实时同步展示（GitHub 直接渲染该文件）。

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
| 集成 | httpx（博查搜索、DeepSeek、高德 Web Service、美团酒旅 Skill） |
| 导出 | openpyxl（XLSX）、python-docx（DOCX） |

## 📁 项目结构

```text
├── app/                  # 应用主代码
│   ├── api/              # 对外 API 路由
│   ├── core/             # 配置与认证
│   ├── db/               # 数据库会话
│   ├── integrations/     # 外部服务集成（搜索、DeepSeek、高德、美团）
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

- 当前版本没有真实支付、网页爬虫或 AI 行程生成；候选发现通过受管理员令牌保护的博查搜索 API 进行，不依赖 LLM 模型，搜索结果不会自动发布。
- 免费目录和 CSV/XLSX 导出统一提供作品名称、地标名称、国家/地区、详细地址、地标简介和信息更新时间；不会输出交通文字、坐标、地图瓦片、审核记录或未发布候选。
- 地标相册仅加载 `data/contributions/landmark_albums/` 中已登记许可信息的本地图片。
- `lite` 与 `premium` 成员可通过带有效 JWT 的 `Authorization: Bearer <token>` 请求，或同源的 `ip_landmark_access_token` Cookie，访问静态点位 API、`/maps/{module}` 地图页和已发布路线；系统始终以数据库会员等级判定权限。
- 任何人可通过 `/contribute` 提交带署名的候选地标；提交不会直接公开。系统记录署名、候选地标和（如已登录）用户 ID，审核发布后才在详情页显示共创者。
- `premium` 成员可通过 `/itineraries` 创建、查看、编辑、删除个性化行程草案，并导出 HTML、DOCX 和 XLSX。预览阶段使用美团酒旅官方 `@meituan-travel/ht-ai` Skill，本地服务始终校验已发布 IP 地标并生成可编辑的基础日程；配置 `DEEPSEEK_API_KEY` 时，DeepSeek 可辅助安排本地 IP 地标顺序，调用失败时回退到确定性生成器；配置高德 Web Service 后，系统会自动使用酒店地址地理编码和步行距离优化当天动线。酒店、交通、门票和餐饮的官方建议须由用户自行确认，系统不会自动下单或写入未确认价格。
- 静态地图只做地标分布与路线顺序参考，不提供实时导航。默认 `MAP_TILE_URL` 使用 OpenStreetMap 标准瓦片 URL：仅限用户主动浏览，禁止预抓取、离线下载或自行抓取瓦片；生产上线前应根据访问量改用符合业务规模与许可条件的地图服务，并保留可见署名和有效 Referer。

## 📦 版本记录

| 版本 | 日期 | 说明 |
| --- | --- | --- |
| v1.0.0 | 2026-08-17 | 初始版本：基础框架、候选数据审核流程、三类地标目录、免费导出、会员地图与线路、个性化行程 |

## 📄 License

项目仓库当前为**公开仓库**，代码与数据对外可见。共创者提交的条目按 [共创贡献规范](docs/共创贡献规范.md) 署名与发布；具体授权条款以仓库声明为准。

