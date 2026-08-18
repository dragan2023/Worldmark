# 03 — GitHub 审核机器人与文件封锁

## 1. 摘要

- 优先级：P0（用户核心诉求 2、3）
- 预计工作量：3–4 人日
- 直接依赖：01（校验脚本）；02（机器人留言引用提示词包路径）
- 阶段目标：用 GitHub Actions 建立「审核机器人」：自动检查 PR 是否只新增条目文件（文件封锁）、复用 01 校验脚本做条目校验、在 PR 上留言评审结果并作为必须通过的状态检查；配合 main 分支保护与 CODEOWNERS，实现共创者无法把非条目改动合入。本阶段只做确定性审查，不引入大模型内容审查。

## 2. 前置阅读

1. 01 阶段 `scripts/validate_contribution_entry.py` 的 `--json` 输出格式。
2. GitHub Actions 官方 action：`actions/checkout`、`actions/setup-python`、`actions/github-script`。
3. GitHub 分支保护（Branch protection rules）与 CODEOWNERS 概念。
4. 当前仓库无 `.github/` 目录，需从零建立；仓库远程为 `dragan2023/Worldmark`。

## 3. 任务详情

### 3.1 文件封锁（路径闸门）

1. 工作流使用 `pull_request_target`（opened/synchronize/reopened）触发：自动在 fork PR 上运行，且能用仓库写权限留言；同时**不把 fork PR 代码检出进工作区**。
2. 第一步用 `actions/checkout@v4` 只检出主分支。GitHub 自 2026-07-20 起在 `pull_request_target` 下禁止 `actions/checkout` 检出 fork PR 的 `refs/pull/<n>/merge`、`refs/pull/<n>/head` 或 fork 提交 SHA；唯一例外 `allow-unsafe-pr-checkout: true` 是官方明确警告的选项，本项目不使用。因此改用 `actions/github-script` 调 `github.rest.pulls.listFiles()` 获取 PR 变更文件列表，写入 `$RUNNER_TEMP/changed-files.txt`，不再依赖 `git diff`。
3. 允许集 = `data/contributions/entries/**`（首期仅条目文件）。
4. 任何越界路径 → 用 `actions/github-script` 在 PR 上留言「仅允许新增条目文件，越界文件：<列表>」，并将该 job 标记失败（失败即不满足分支保护、不可合入）。
5. 说明：GitHub 无法对 fork PR 做真正的文件级写锁定；「机器人路径检查（必须通过）+ main 分支保护（必须通过才能合入）+ CODEOWNERS」是平台内最稳妥、最简单的封锁组合，效果等同封锁其他文件。

### 3.2 条目校验检查

1. 同一工作流新增 `validate` job：`actions/setup-python`（Python 3.13）→ `pip install -r requirements.txt` → 校验 PR 新增条目。
2. 由于不检出 PR 代码，先由 `actions/github-script` 用 `github.rest.repos.getContent()`（`ref = github.event.pull_request.head.sha`）逐个拉取 PR 中的条目 CSV 内容，按原相对路径写入 `$GITHUB_WORKSPACE/data/contributions/entries/`，再运行 `scripts/review_logic.py review` 复用 01 阶段校验逻辑；重复检查会同时覆盖主分支既有条目与 PR 新增条目。
3. 任一文件 invalid → 留言列出具体错误（列级、三段式、重复等）并请求修改；全部 valid → 留言「校验通过，等待维护者人工确认」。
4. `validate` job 的最终结果为分支保护要求的状态检查（命名为 `validate-contribution`）。
5. 留言中记录 PR 作者 GitHub 用户名（`github.event.pull_request.user.login`），作为后续署名与共创者名单的依据（见 04 阶段）。

### 3.3 分支保护与 CODEOWNERS

1. 新增 `.github/CODEOWNERS`：
   - `* @dragan2023`
   - `.github/ @dragan2023`
   - `app/ @dragan2023`
   - `tests/ @dragan2023`
   - `alembic/ @dragan2023`
   - `scripts/ @dragan2023`
   - `data/seed/ @dragan2023`
   - `data/contributions/contributors.json @dragan2023`
   - `docs/ @dragan2023`
2. 在仓库 Settings → Branches 为 `main` 启用（维护者手动配置并记录到文档）：
   - Require a pull request before merging（至少 1 个维护者批准）
   - Require status checks to pass（勾选 `validate-contribution`）
   - Require conversation resolution
   - Restrict who can push to matching branches（仅维护者）
   > 实际配置记录（2026-08-18）：已启用 `validate-contribution` 与 `文件封锁检查` 两个状态检查、strict（PR 必须基于最新 main）、enforce_admins；「至少 1 个维护者批准 / conversation resolution / restrict push」为可选增强项，当前未启用。完整配置方法与检查名见 05 阶段 §3.5。
3. 效果：共创者 PR 即使改动其他文件也无法合入；`.github/`、`app/`、`tests/` 等配置与代码变更必须由维护者处理。

### 3.4 机器人行为规范与可测性

1. 机器人只在 PR 打开/更新/重开时触发；绝不自动合并、绝不自动批准。
2. 评审留言使用固定模板（表格式），包含：越界文件检查、逐文件校验结果、重复检查、来源可达性提醒、PR 作者署名、下一步指引（指向 `docs/共创提示词包/00_使用说明.md`）。
3. 把「越界判断」「留言模板生成」抽成纯函数（如 `tests/scripts/test_review_logic.py` 内联实现），用 pytest 覆盖，避免每次改模板都要在真实 Actions 上验证。

## 4. 精确文件范围

1. 新增：`.github/workflows/review-contribution.yml`、`.github/CODEOWNERS`。
2. 新增：`tests/scripts/test_review_logic.py`（路径闸门与留言模板的本地测试）。
3. 修改：`README.md`（增加「如何参与共创」入口小节）。

## 5. 示例：校验留言模板

```text
## 共创条目审核结果
- PR 作者：@<github_username>
- 越界文件检查：✅ 仅新增条目文件
- 条目校验：❌ 1 个文件未通过
  - `game/black-myth-wukong--foguang-temple.csv`：description 缺少「现实地标介绍：」三段式前缀
- 重复检查：✅ 无重复
- 来源可达性：⚠️ 未启用（可选）
请按 `docs/共创提示词包/00_使用说明.md` 修复后推送更新，机器人会自动复查。
```

## 6. 禁止修改与风险红线

1. 机器人绝不自动合并、绝不自动批准；不调用任何大模型做内容审查。
2. 机器人只读代码与数据，不做 `git push` 回写（回写属于 04 的发布流水线）。
3. 分支保护需人工复核，避免「机器人账号被授予批准/合并权限」的漏洞；机器人使用 `github-actions[bot]` 且不授予批准权限。
4. 不把 repo secrets 打印到留言或日志。
5. 不在 `pull_request_target` 工作流中检出 fork PR 代码，不使用 `actions/checkout` 的 `allow-unsafe-pr-checkout` 选项。

## 7. 验收标准

- [ ] 测试分支仅新增合法 entry 文件 → 机器人留言「校验通过」且 `validate-contribution` 为绿色。
- [ ] 同一分支再修改 `app/main.py` → 机器人留言越界文件清单且检查为红色，无法满足分支保护。
- [ ] 缺字段/缺三段式/重复条目的 entry → 机器人留言具体错误，修正后复查转绿。
- [ ] 维护者可合入合法测试 PR；非维护者 push 到 `main` 被分支保护拒绝。
- [ ] 修改 `.github/`、`app/` 或 `data/contributions/contributors.json` 的 PR 触发 CODEOWNERS 要求维护者审批。
- [ ] 机器人留言包含 PR 作者 GitHub 用户名。
- [ ] `tests/scripts/test_review_logic.py` 全绿。
