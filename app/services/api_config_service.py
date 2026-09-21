"""API 配置服务：盘点内置外部服务客户端，支持在本地 .env 中快捷写入密钥。

面向开源自托管场景：

- 快照（只读）：列出每个内置客户端的用途、所需环境变量、配置状态与官方申请入口。
  密钥只做掩码展示，绝不回传完整值。
- 写入：仅允许在本地/开发环境（APP_ENV=production 时由 API 层拒绝）把用户填写的
  密钥更新进项目根目录 .env（保留既有行序与注释），并刷新运行时配置缓存。

设计约束：本模块不持有任何真实密钥副本，掩码与状态判断都以 Settings 的
SecretStr 现场计算；.env 写入是唯一落盘点。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from app.core.config import Settings, get_settings

# .env 不存在时创建用的文件头
_ENV_FILE_HEADER = (
    "# 由 Worldmark API 配置页维护的本地密钥文件。\n"
    "# 请勿把真实密钥提交到仓库；泄露后请到对应平台吊销并重新申请。\n"
)

# 写入值只允许单行普通文本，禁止换行与注释符
_FORBIDDEN_VALUE_PATTERN = re.compile(r"[\r\n#]")


@dataclass(frozen=True)
class ConfigField:
    """API 配置页对外暴露的一个环境变量。"""

    env: str
    label: str
    secret: bool = True
    placeholder: str = ""
    hint: str = ""


@dataclass(frozen=True)
class ApiClientSpec:
    """一个内置外部服务客户端的元数据描述。"""

    id: str
    name: str
    vendor: str
    purpose: str
    features: tuple[str, ...]
    fields: tuple[ConfigField, ...]
    apply_url: str | None = None
    docs_url: str | None = None
    requirement: str = "recommended"  # required | recommended | optional
    note: str | None = None


CLIENT_SPECS: tuple[ApiClientSpec, ...] = (
    ApiClientSpec(
        id="llm",
        name="LLM 大模型客户端",
        vendor="OpenAI 兼容协议（默认 DeepSeek）",
        purpose="AI 行程生成与「一键入库」地标智能分析，通过 OpenAI 兼容 /chat/completions 接口调用。",
        features=("AI 行程生成", "一键入库智能分析"),
        fields=(
            ConfigField(
                env="DEEPSEEK_API_KEY",
                label="LLM API Key",
                secret=True,
                placeholder="sk-...",
                hint="不限于 DeepSeek：任何 OpenAI 兼容服务商的 Key 均可填入此处。",
            ),
            ConfigField(
                env="DEEPSEEK_BASE_URL",
                label="接口地址",
                secret=False,
                placeholder="https://api.deepseek.com",
                hint="更换服务商时同步修改，例如 https://api.siliconflow.cn。",
            ),
            ConfigField(
                env="DEEPSEEK_MODEL",
                label="模型名",
                secret=False,
                placeholder="deepseek-chat",
                hint="以服务商文档提供的模型名为准。",
            ),
        ),
        apply_url="https://platform.deepseek.com/api_keys",
        docs_url="https://api-docs.deepseek.com/zh-cn/",
        requirement="recommended",
        note="未配置时 AI 行程生成回退到本地确定性生成器，「一键入库」不可用。",
    ),
    ApiClientSpec(
        id="amap",
        name="高德 Web 服务 Key",
        vendor="高德开放平台",
        purpose="地址地理编码、POI 检索、步行路线规划与酒店坐标补全（境内自动 GCJ-02 转 WGS-84 纠偏）。",
        features=("地标坐标补全", "POI 检索", "步行距离与动线优化"),
        fields=(
            ConfigField(
                env="AMAP_WEB_SERVICE_API_KEY",
                label="Web 服务 Key",
                secret=True,
                placeholder="在高德控制台创建应用后获取",
                hint="需创建「Web 服务」类型 Key，而非 Web 端(JS API) Key。",
            ),
        ),
        apply_url="https://console.amap.com/dev/key/app",
        docs_url="https://lbs.amap.com/api/webservice/create-project-and-key",
        requirement="recommended",
        note="未配置时坐标解析回退 OpenStreetMap Nominatim，境内精度可能下降。",
    ),
    ApiClientSpec(
        id="meituan",
        name="美团酒旅官方 Skill",
        vendor="美团开发者中心",
        purpose="生成行程草案并提供住宿 / 交通 / 门票价格参考，通过官方 ht-ai Skill 调用。",
        features=("行程草案", "价格参考补全"),
        fields=(
            ConfigField(
                env="MEITUAN_HT_TOKEN",
                label="Skill Token",
                secret=True,
                placeholder="在美团开发者中心完成实名认证后获取",
                hint="旧别名 MEITUAN_TRAVEL_TOKEN 仍兼容，优先使用 MEITUAN_HT_TOKEN。",
            ),
        ),
        apply_url="https://developer.meituan.com/zh/v2/dev/token",
        requirement="optional",
        note="调用依赖本机 Node.js/npx，首次运行自动拉取 @meituan-travel/ht-ai；未配置时仅跳过价格参考。",
    ),
    ApiClientSpec(
        id="bocha",
        name="博查 AI 搜索",
        vendor="博查开放平台",
        purpose="候选地标联网检索、行程资料检索与「一键入库」来源核实。",
        features=("候选发现", "行程资料检索", "一键入库来源核实"),
        fields=(
            ConfigField(
                env="BOCHA_API_KEY",
                label="API Key",
                secret=True,
                placeholder="在博查开放平台创建后获取",
            ),
        ),
        apply_url="https://open.bochaai.com/api-keys",
        requirement="optional",
        note="未配置时「一键入库」将跳过联网核实，来源可信度降低并会给出提示。",
    ),
    ApiClientSpec(
        id="maptile",
        name="地图瓦片服务",
        vendor="OpenStreetMap（默认）/ 高德等合规服务",
        purpose="目录地图与行程地图的瓦片渲染。",
        features=("目录地图", "行程地图"),
        fields=(
            ConfigField(
                env="MAP_TILE_URL",
                label="瓦片地址模板",
                secret=False,
                placeholder="https://tile.openstreetmap.org/{z}/{x}/{y}.png",
                hint="必须包含 {z}/{x}/{y} 占位符；生产前请评估所选服务的许可与流量。",
            ),
        ),
        requirement="optional",
        note="未配置时地图页提示「地图瓦片服务未配置」，其余功能不受影响。",
    ),
)

# 允许通过配置页写入的全部环境变量名
WRITABLE_ENV_NAMES: frozenset[str] = frozenset(
    field.env for spec in CLIENT_SPECS for field in spec.fields
)


def mask_secret(value: str | None) -> str:
    """返回可安全展示的掩码，绝不泄露完整密钥。"""
    text = (value or "").strip()
    if not text:
        return ""
    if len(text) <= 8:
        return "****"
    return f"{text[:4]}****{text[-4:]}"


def _raw_value(settings: Settings, env: str) -> str | None:
    raw = getattr(settings, env.lower(), None)
    if raw is None:
        return None
    if isinstance(raw, str):
        return raw
    return raw.get_secret_value()


def _configured(settings: Settings, env: str) -> bool:
    value = _raw_value(settings, env)
    return bool(value and value.strip())


def field_snapshot(spec: ApiClientSpec, settings: Settings) -> list[dict[str, object]]:
    fields: list[dict[str, object]] = []
    for field in spec.fields:
        configured = _configured(settings, field.env)
        masked = ""
        if configured:
            masked = mask_secret(_raw_value(settings, field.env)) if field.secret else str(_raw_value(settings, field.env))
        fields.append(
            {
                "env": field.env,
                "label": field.label,
                "secret": field.secret,
                "hint": field.hint,
                "placeholder": field.placeholder,
                "configured": configured,
                "masked": masked,
            }
        )
    return fields


def _client_status(spec: ApiClientSpec, settings: Settings) -> str:
    """客户端开关只看主密钥（首个 secret 字段）。"""
    primary = next((field for field in spec.fields if field.secret), None)
    if primary is None:
        return "configured"
    return "configured" if _configured(settings, primary.env) else "missing"


def build_snapshot(settings: Settings) -> dict[str, object]:
    """构建配置页渲染用的只读状态快照。"""
    clients: list[dict[str, object]] = []
    for spec in CLIENT_SPECS:
        clients.append(
            {
                "id": spec.id,
                "name": spec.name,
                "vendor": spec.vendor,
                "purpose": spec.purpose,
                "features": list(spec.features),
                "requirement": spec.requirement,
                "apply_url": spec.apply_url,
                "docs_url": spec.docs_url,
                "note": spec.note,
                "status": _client_status(spec, settings),
                "fields": field_snapshot(spec, settings),
            }
        )
    return {
        "app_env": settings.app_env,
        "can_edit": not settings.is_production,
        "clients": clients,
    }


def update_env_file(values: dict[str, str], env_path: Path | None = None) -> Path:
    """把键值对写入项目 .env，保留既有行序与注释；空值表示清空该变量。

    环境变量名白名单由 API 层与这里共同把关；本函数额外拒绝含换行、
    井号等非法字符的值，防止注入任意 .env 行。
    """
    target = env_path or (Path.cwd() / ".env")
    clean: dict[str, str] = {}
    for env, value in values.items():
        if env not in WRITABLE_ENV_NAMES:
            raise ValueError(f"不支持写入的环境变量：{env}")
        text = value.strip()
        if _FORBIDDEN_VALUE_PATTERN.search(text):
            raise ValueError(f"{env} 的值包含非法字符（换行、井号等）。")
        clean[env] = text

    existing_lines: list[str] = []
    if target.exists():
        existing_lines = target.read_text(encoding="utf-8").splitlines()

    lines = list(existing_lines)
    for env, value in clean.items():
        lines = _upsert_line(lines, env, value)

    content = "\n".join(lines)
    if content and not content.endswith("\n"):
        content += "\n"
    if not existing_lines:
        content = _ENV_FILE_HEADER + content
    target.write_text(content, encoding="utf-8")
    return target


def _upsert_line(lines: list[str], env: str, value: str) -> list[str]:
    """替换既有赋值行（多余重复赋值一并去除），没有则在文件尾追加。"""
    pattern = re.compile(rf"^\s*{re.escape(env)}\s*=")
    output: list[str] = []
    replaced = False
    for line in lines:
        if pattern.match(line):
            if not replaced:
                output.append(f"{env}={value}")
                replaced = True
        else:
            output.append(line)
    if not replaced:
        output.append(f"{env}={value}")
    return output


def refresh_runtime_settings() -> None:
    """清空缓存的 Settings，让后续请求读到新的 .env。"""
    get_settings.cache_clear()


def run_client_probe(client_id: str, settings: Settings) -> tuple[bool, str]:
    """对指定客户端做一次轻量连通性探测，返回 (是否可用, 说明)。

    说明：meituan 只检查本地可用性（Token + npx），不实际调用官方 Skill，
    避免探测动作本身产生外部请求与费用。
    """
    from app.integrations.amap_web_service import (
        AmapConfigurationError,
        AmapServiceError,
        AmapWebService,
    )
    from app.integrations.deepseek_client import (
        DeepSeekClient,
        DeepSeekClientError,
        DeepSeekConfigurationError,
    )
    from app.integrations.meituan_travel_mcp import MeituanTravelMcp
    from app.integrations.search.bocha_web_search import (
        BochaWebSearchProvider,
        SearchConfigurationError,
        SearchProviderError,
    )

    if client_id == "amap":
        key = settings.amap_web_service_api_key
        if not key or not key.get_secret_value().strip():
            return False, "未配置 AMAP_WEB_SERVICE_API_KEY。"
        try:
            location = AmapWebService(key.get_secret_value().strip()).geocode("北京市东城区")
        except AmapConfigurationError as exc:
            return False, str(exc)
        except AmapServiceError as exc:
            return False, f"高德拒绝了请求：{exc}"
        if location:
            return True, f"地理编码正常，示例地址返回坐标 {location}。"
        return False, "高德服务可达，但示例地址未解析出坐标，请确认 Key 类型为「Web 服务」且已开通所需服务。"

    if client_id == "llm":
        key = settings.deepseek_api_key
        if not key or not key.get_secret_value().strip():
            return False, "未配置 DEEPSEEK_API_KEY。"
        client = DeepSeekClient(
            key.get_secret_value().strip(),
            base_url=settings.deepseek_base_url,
            model=settings.deepseek_model,
            thinking=settings.deepseek_thinking,
        )
        try:
            reply = client.chat([{"role": "user", "content": "连接测试，请只回复：正常"}])
        except DeepSeekConfigurationError as exc:
            return False, str(exc)
        except DeepSeekClientError as exc:
            return False, f"LLM 请求失败：{exc}"
        return True, f"模型 {settings.deepseek_model} 响应正常：{reply[:40]}"

    if client_id == "meituan":
        token = settings.effective_meituan_travel_token
        if not token or not token.get_secret_value().strip():
            return False, "未配置 MEITUAN_HT_TOKEN。"
        skill = MeituanTravelMcp(token.get_secret_value().strip())
        if not skill.is_available():
            return False, "Token 已配置，但本机未检测到 npx（请安装 Node.js）。"
        return True, "Token 与 npx 均就绪（未实际调用官方 Skill，避免产生外部请求）。"

    if client_id == "bocha":
        key = settings.bocha_api_key
        if not key or not key.get_secret_value().strip():
            return False, "未配置 BOCHA_API_KEY。"
        provider = BochaWebSearchProvider(key.get_secret_value().strip())
        try:
            result = provider.search("北京 旅游")
        except SearchConfigurationError as exc:
            return False, str(exc)
        except SearchProviderError as exc:
            return False, f"博查请求失败：{exc}"
        return True, f"检索正常，示例查询返回 {len(result.references)} 条结果。"

    if client_id == "maptile":
        url = (settings.map_tile_url or "").strip()
        if not url:
            return False, "未配置 MAP_TILE_URL。"
        if "{z}" not in url or "{x}" not in url or "{y}" not in url:
            return False, "瓦片地址缺少 {z}/{x}/{y} 占位符。"
        return True, f"瓦片地址已配置：{url}"

    raise ValueError(f"未知的客户端：{client_id}")
