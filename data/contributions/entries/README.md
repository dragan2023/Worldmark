# 共创条目目录（data/contributions/entries/）

本目录是「Harness PR 共创」流程的唯一数据入口：**每条共创地标 = 一个独立 CSV 文件**。

## 目录结构

```text
data/contributions/entries/
├─ literature/   文学类 IP 地标条目
├─ game/         游戏类 IP 地标条目
├─ screen/       影视剧类 IP 地标条目
└─ archive/      已导入条目的归档（由发布流水线维护，共创者请勿改动）
```

## 规则

1. 每条地标一个 CSV 文件，文件必须放在与 `ip_type` 一致的子目录下（`literature` / `game` / `screen`）。
2. 文件命名：`<work-slug>--<landmark-slug>.csv`，全小写、单词用连字符分隔，例如 `game/black-myth-wukong--foguang-temple.csv`。
3. 表头必须与 `data/templates/landmark_candidate_template.csv` 完全一致（22 列），且文件只能有一行数据。
4. 字段规则遵循 `docs/数据采集规范.md`；`description` 必须为「在作品中的重要地位：… 主要出现的情节：… 现实地标介绍：…」三段式原创内容；`source_url` 必须为可访问的 HTTP/HTTPS 来源；坐标缺失时留空。
5. 提交前请运行本地校验：

```powershell
.\.venv\Scripts\python.exe scripts\validate_contribution_entry.py --file <你的条目文件> --json
```

## 禁止事项

- 不得修改本目录之外的任何文件（`app/`、`tests/`、`alembic/`、`scripts/`、`data/seed/`、`data/contributions/contributors.json`、`.github/`、`docs/` 等一律禁止改动）。
- 不得修改或删除他人的条目文件。
- 不得提交未经核实的来源、地址与交通/营业信息；不得复制受版权保护的内容。
