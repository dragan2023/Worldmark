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
- 🤖 **一键入库 AI Agent**：输入「作品名 + 地标名」，AI 自动解析意图、联网核实、生成三段式简介并补全坐标，一键生成候选条目（`/intake`）
- 🖼️ **地标相册管理**：多图上传组件支持点击放大、右上角 × 移除与信息编辑；内置 AI 找图（LLM 生成检索词 + Wikimedia Commons 免费授权图库检索下载）产出的候选图片落在同一组件中，Commons 图自动带许可与作者署名，人工确认后提交才会对外展示
- 🔑 **API 配置页**：内置美团酒旅、高德、LLM（OpenAI 兼容）等客户端的状态总览，支持在页面填 Key 快捷写入本机 `.env`，并提供各平台申请入口（`/settings/api`）
- 🤝 **共创贡献**：登录会员在 `/intake` 用一句自然语言一键入库候选地标（AI 解析 + 联网核实 + 自动补全），审核发布后展示提交者署名并自动升级账号

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

### 一键入库（AI 生成候选条目）

打开 `/intake`「一键入库」页，用一句自然语言描述「作品 + 地标」并提交，例如：

```text
《黑神话：悟空》 小西天
金庸《射雕英雄传》 华山
```

内置 AI Agent 会依次完成：解析输入 → 博查联网核实现实资料 → 生成三段式简介与结构化字段 → 高德/Nominatim 地理编码补全坐标 → 以**候选（candidate）状态入库**。页面会展示生成结果、参考来源与需要人工复核的提示；候选条目不会直接公开，需管理员审核发布后才会出现在目录中。

- 需要 `DEEPSEEK_API_KEY`（或任意 OpenAI 兼容 LLM Key）才能运行；未配置时页面会引导前往「API 配置」页。
- `BOCHA_API_KEY`、`AMAP_WEB_SERVICE_API_KEY` 可选：未配置时将跳过联网核实或坐标补全，并在结果中给出警告，绝不编造来源与坐标。
- 相同「作品 + 地标名 + 地址」的组合会被去重拦截（HTTP 409）。

对应的 API 为 `POST /api/v1/agent/landmarks/intake`，请求体 `{"input": "作品名 地标名"}`，需登录会员身份。

### 地标相册：上传、AI 找图与提交

地标详情页的「地标相册」区块提供「管理相册」入口（也可直接访问 `/landmarks/{id}/album/edit`，候选地标同样可用）：

1. **上传图片**：多选上传 JPG / PNG / WebP / AVIF（单张 ≤ 8MB，单次 ≤ 12 张），图片先进入本机暂存区 `uploads/landmark_albums/`；
2. **AI 找图**：LLM 生成 Commons 友好的短检索词（中文原名 + 地名罗马化 + 区县消歧）→ Wikimedia Commons 图片检索 → LLM 按标题与来源剔除同名异地干扰 → 自动下载至多 6 张候选图。Commons 图自带自由授权（如 CC BY-SA）与作者署名，下载即自动填好许可与来源链接；与上传图片落在同一组件中，不满意的直接点 × 移除；
3. **编辑与确认**：点击小图放大预览，并编辑图片说明（必填）、图注、署名、版权与来源链接；点图片右上角 × 移除（已发布图片标记移除，提交后移入 `_trash` 回收站）；
4. **提交相册**：确认后一键落库——暂存文件移入正式相册目录并原子化更新 `manifest.json`，立即在详情页展示。

> AI 找图的图片来源为 Wikimedia Commons（免 Key、自由授权），`DEEPSEEK_API_KEY` 用于检索词生成与候选去歧义排序（未配置时直接用地标名检索）；博查（`BOCHA_API_KEY`）仅用于「一键入库」的联网核实（其图片搜索端点暂未开放）。上传图片默认带「自行确认版权」标记，展示即代表维护者确认可用。

## 🔑 配置 API Key（地图与旅游计划）

地图展示与个性化旅游计划会调用外部地图 / AI / 旅游服务。**不配置任何 Key 也能正常浏览目录与导出数据**，但以下功能需要对应的 Key 才会启用完整能力：

> **快捷方式**：启动应用后打开 [`/settings/api`](http://127.0.0.1:8000/settings/api)「API 配置」页，可以在这里查看每个内置客户端（LLM / 高德 / 美团 / 博查 / 地图瓦片）的配置状态与掩码，直接填入 Key 保存到本机 `.env`（生产环境 `APP_ENV=production` 时网页写入会被禁用），也可以点「测试连通」即时验证，各客户端均附官方申请链接。下文为手工配置方式。

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

欢迎为 Worldmark 贡献新的文学 / 游戏 / 影视地标条目。共创已改为**应用内一键入库**：不需要 Fork 仓库、不需要手写 CSV、不需要开 Pull Request——注册登录后，用一句自然语言描述即可。

1. **注册 / 登录**（[注册页面](/register)）：注册即为二级用户，已具备一键入库权限。
2. **打开 [`/intake`「一键入库」页](/intake)**：用一句自然语言描述「作品 + 地标」，例如「情书 小樽运河」。
3. **AI 自动补全**：解析作品与地标 → 联网核实现实资料 → 生成三段式原创简介与结构化字段 → 地理编码补全坐标，最终以**候选（candidate）状态**入库，不会直接公开。
4. **人工审核后发布**：管理员在 `/admin` 复核并发布为 `verified` 后，条目才出现在目录、导出与地图中，详情页展示提交者署名。
5. **贡献者自动升级**：你提交的条目被发布后，账号自动升为一级用户（解锁个性化行程），只升不降、幂等。

> 候选条目不会出现在公开目录、导出或地图中；相同「作品 + 地标名 + 地址」的组合会被去重拦截；条目必须提供可访问来源与三段式原创简介。

规范与字段要求见 [`docs/共创贡献规范.md`](docs/共创贡献规范.md) 与 [`docs/数据采集规范.md`](docs/数据采集规范.md)；LLM / 联网核实 / 坐标补全的 Key 配置见上文「一键入库（AI 生成候选条目）」小节。

## 👥 用户系统（注册 / 角色 / 密钥隔离）

应用内置三级用户体系（见 docs/用户系统开发计划.md）：

| 角色 | 权限 |
| --- | --- |
| **管理员**（admin） | 全部功能 + 用户管理（/admin/users）+ 条目审核/修改/下架/删除 + 系统密钥配置（/settings/api，未自配时可回落系统密钥） |
| **一级用户**（level1） | 二级权限 + **个性化行程**（生成 / 导出 / 美团数据） |
| **二级用户**（level2） | 浏览地图与目录 + **一键入库**提交候选地标 + 相册管理 |

- 注册即成为二级用户（[注册页面](/register)），**登录标识为自定义用户名**（3-32 位英文/数字/下划线，邮箱仅作资料与找回联系用）；贡献的地标被管理员**发布后自动升为一级用户**（只升不降，幂等）。
- 登录采用 JWT（HttpOnly Cookie，8 小时）+ Bearer 双通道；封禁即时生效，已签发的 token 也会被拒绝。
- 登录接口内置内存级限速：同一 IP 15 分钟内连续失败 8 次将返回 429。

### 🔐 按用户隔离密钥

需要调用第三方付费服务（DeepSeek / 高德 / 博查 / 美团）的功能遵循 **"自己的密钥自己配"**：

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

- [共创贡献规范](docs/共创贡献规范.md)
- [数据采集规范](docs/数据采集规范.md)
- [来源分级与审核准则](docs/来源分级与审核准则.md)
- [隐私与数据保留说明](docs/隐私与数据保留说明.md)

## 📝 范围与说明

- 当前版本没有真实支付、网页爬虫；候选发现通过受管理员令牌保护的博查搜索 API 进行，搜索结果不会自动发布。未配置 LLM API Key（`DEEPSEEK_API_KEY`，OpenAI 兼容接口，不限于 DeepSeek）时，行程生成回退到确定性本地生成器。
- 免费目录和 CSV/XLSX 导出统一提供作品名称、地标名称、国家/地区、详细地址、地标简介和信息更新时间；不会输出交通文字、坐标、地图瓦片、审核记录或未发布候选。
- 地标相册仅加载 `data/contributions/landmark_albums/` 中已登记许可信息的本地图片。
- 所有用户（无需登录）均可访问静态点位 API、`/maps/{module}` 地图页、已发布路线与个性化行程；系统不再按会员等级限制功能。
- 共创采用应用内一键入库：登录会员在 `/intake` 用自然语言提交候选地标，AI 负责解析、联网核实、生成三段式简介并补全坐标，条目以 candidate 状态入库；经管理员审核发布后才公开，并向提交者署名、自动升级账号。仓库不再接收共创 PR，也不再有 PR 审核机器人。
- 所有用户均可通过 `/itineraries` 创建、查看、编辑、删除个性化行程草案，并导出 HTML、DOCX 和 XLSX。预览阶段使用美团酒旅官方 `@meituan-travel/ht-ai` Skill，本地服务始终校验已发布 IP 地标并生成可编辑的基础日程；配置 LLM API Key（`DEEPSEEK_API_KEY`，OpenAI 兼容接口，不限于 DeepSeek）时，可辅助安排本地 IP 地标顺序，调用失败时回退到确定性生成器；配置高德 Web Service 后，系统会自动使用酒店地址地理编码和步行距离优化当天动线。酒店、交通、门票和餐饮的官方建议须由用户自行确认，系统不会自动下单或写入未确认价格。
- 静态地图只做地标分布与路线顺序参考，不提供实时导航。默认 `MAP_TILE_URL` 使用 OpenStreetMap 标准瓦片 URL：仅限用户主动浏览，禁止预抓取、离线下载或自行抓取瓦片；生产上线前应根据访问量改用符合业务规模与许可条件的地图服务，并保留可见署名和有效 Referer。

## 📦 版本记录

| 版本 | 日期 | 说明 |
| --- | --- | --- |
| v1.0.0 | 2026-08-17 | 初始版本：基础框架、候选数据审核流程、三类地标目录、免费导出、会员地图与线路、个性化行程 |

## 📄 License

项目仓库当前为**公开仓库**，代码与数据对外可见。共创者提交的条目按 [共创贡献规范](docs/共创贡献规范.md) 审核、署名与发布；具体授权条款以仓库声明为准。

