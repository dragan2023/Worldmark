# 01 — 官方 Skill 归档与运行时适配

## 1. 摘要

优先级：高。预计工作量：中。直接依赖：无。阶段目标：归档用户下载的官方 Skill，并让后端通过其规定的 `@meituan-travel/ht-ai` CLI、Token 名称和 raw JSON 输出方式调用服务。

## 2. 前置阅读

1. `docs/第三方Skills/美团酒旅/official-skill/SKILL.md`
2. `app/integrations/meituan_travel_mcp.py`
3. `app/core/config.py`
4. `tests/services/test_travel_integrations.py`

## 3. 任务详情

2.1 将下载包中的 `SKILL.md` 和 `channel.json` 移至 `docs/第三方Skills/美团酒旅/official-skill/`，不纳入 `__MACOSX` 元数据。

2.2 新建或改造官方适配器，以列表参数调用：

```text
npx @meituan-travel/ht-ai@latest query
  --query <完整旅行查询>
  --origin-query <用户完整原始查询>
  --channel meituan-developer
  --city <城市>
  -o json
```

2.3 子进程仅设置 `MEITUAN_HT_TOKEN`、`MEITUAN_RAW_JSON=1` 和最小必要环境；不得写入用户目录配置文件。适配器返回 `raw_json`、格式化内容、来源、查询时间和调用版本，不打印 Token。

2.4 将 `Settings` 与 `.env.example` 增加 `MEITUAN_HT_TOKEN`；实现从旧 `MEITUAN_TRAVEL_TOKEN` 的兼容读取并在运行文档中说明迁移方式。

2.5 用模拟进程覆盖正常结果、exit 3、超时、无效 JSON 和命令缺失。

## 4. 禁止修改与风险红线

1. 不继续使用旧 `mttravel` CLI 作为新方案主路径。
2. 不从官方包中提取、反编译或硬编码服务端点。
3. 不让测试访问网络或真实本地 Token。

## 5. 验收标准

- [ ] 官方包位于文档归档目录，项目根目录不保留重复的可执行/说明副本。
- [ ] 适配器按官方 Skill 参数调用 `ht-ai`，并请求 raw JSON。
- [ ] 令牌不会出现在异常、日志、响应或测试快照中。
- [ ] `tests/services/test_travel_integrations.py` 在离线环境通过。
