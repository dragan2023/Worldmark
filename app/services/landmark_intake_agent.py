"""「一键入库」AI Agent：从自然语言输入生成 IP 地标候选条目。

编排流程（每个组件都可注入替身，测试完全离线）：

1. parse    —— LLM 从「作品名 + 地标名」自然语言中解析结构化意图；
2. research —— 博查检索作品与地标的现实资料（未配置时跳过并告警）；
3. compose  —— LLM 基于检索结果生成候选条目字段（三段式简介、来源取自检索结果）；
4. ground   —— 高德/Nominatim 地理编码补全坐标（失败不编造，仅告警）；
5. persist  —— 复用 LandmarkImportService 以 CANDIDATE 状态入库，天然获得去重与来源关联。

数据护栏（与项目既有数据规范一致）：

- 来源 URL 优先逐字取自联网检索结果；未配置检索时才允许模型给出，
  并降级告警提示人工核实；
- 地理编码失败一律留空坐标，绝不编造；
- 入库状态固定为 candidate，公开仍需管理员审核发布。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.integrations.deepseek_client import DeepSeekClient
from app.models.enums import IPType
from app.services.geocoding import GeocodingService
from app.services.import_landmarks import CandidateRow, LandmarkImportService
from app.services.search_discovery import SearchDiscoveryService

PARSE_SYSTEM_PROMPT = """你是 IP 地标目录的数据入口助手。用户会给出一段自然语言，通常包含「作品名（书名/游戏名/影视剧名）」与「地标名」。请只输出 JSON 对象：
{"ip_type": "literature|game|screen", "work_title": "作品规范名", "aliases": "作品别名，逗号分隔，可为空字符串", "landmark_name": "地标名", "landmark_kind": "地标类型（如 古建筑/老街/博物馆/自然景观），可为空字符串", "notes": "补充说明"}
规则：
1. ip_type 必须是 literature（文学）、game（游戏）、screen（影视）之一；无法判断时按最可能的类型给出并在 notes 说明。
2. 若输入未指明地标名，请选择该作品最具代表性的现实取景地或原型地，并在 notes 中注明「自动选择」。
3. 只输出 JSON，不要 markdown 或解释文字。"""

COMPOSE_SYSTEM_PROMPT = """你是 IP 地标目录的资深资料编辑。请基于给定的作品、地标与联网检索参考，生成一条候选地标条目，只输出 JSON 对象：
{"ip_type": "literature|game|screen", "work_title": "作品名", "aliases": "别名，可为空字符串", "landmark_name": "地标名", "landmark_kind": "地标类型", "country_code": "两位 ISO 国家码", "country_name": "国家/地区中文名", "province_name": "省/州，可为空字符串", "city_name": "城市，可为空字符串", "district_name": "区县，可为空字符串", "normalized_address": "完整可地理编码的现实地址", "description": "三段式简介", "transit_text": "交通说明，可为空字符串", "source_url": "来源链接", "source_title": "来源标题", "source_publisher": "来源机构", "source_type": "official|news|encyclopedia|blog|other"}
硬性规则：
1. description 必须是原创三段式：第一段「在作品中的重要地位」，第二段「主要出现的情节」，第三段「现实地标介绍」，总长不少于 150 字，用换行分隔三段。
2. 提供了参考列表时，source_url 必须逐字取自参考列表中的 url，source_title/source_publisher 取自同一条目，source_type 从 official/news/encyclopedia/blog/other 中选择最贴切者；禁止编造列表外的链接。
3. 未提供参考列表时，source_url 使用最权威的公开资料页（官方网站或百科词条），source_type 标为 other。
4. normalized_address 要能被地图服务解析：境内用「省+市+区县+街道+名称」，境外用「街道, 城市, 国家」。
5. 没有把握的信息留空字符串，禁止编造。
6. 只输出 JSON，不要 markdown 或解释文字。"""


@dataclass(frozen=True)
class IntakeStep:
    """一次入库编排中单步的执行记录。"""

    name: str
    status: str  # ok | skipped | failed
    detail: str = ""


@dataclass(frozen=True)
class IntakeOutcome:
    """入库结果：新建候选地标及其生成过程信息。"""

    landmark_id: int
    work_title: str
    ip_type: str
    landmark_name: str
    address: str
    latitude: float | None
    longitude: float | None
    description: str
    source_url: str
    warnings: list[str] = field(default_factory=list)
    steps: list[IntakeStep] = field(default_factory=list)
    search_run_id: int | None = None


class LandmarkIntakeError(RuntimeError):
    """AI 分析或字段校验失败，输入需要人工修正。"""


class LandmarkIntakeUnavailable(LandmarkIntakeError):
    """依赖的外部客户端未配置（如 LLM Key 缺失），属于环境问题。"""


class LandmarkIntakeDuplicate(LandmarkIntakeError):
    """相同作品、地标与地址的条目已经存在。"""


class LandmarkIntakeAgent:
    """把「作品名 + 地标名」的自然语言输入一键变成候选地标条目。"""

    version = "intake-agent-v1"

    def __init__(
        self,
        db: Session,
        settings: Settings,
        *,
        llm: DeepSeekClient | None = None,
        search_service: SearchDiscoveryService | None = None,
        geocoder: GeocodingService | None = None,
    ) -> None:
        self._db = db
        self._settings = settings
        self._llm = llm
        self._search_service = search_service
        self._geocoder = geocoder

    # ---------- 组件装配（未注入时按配置现场构建） ----------

    def _ensure_llm(self) -> DeepSeekClient:
        if self._llm is None:
            key = self._settings.deepseek_api_key
            if not key or not key.get_secret_value().strip():
                raise LandmarkIntakeUnavailable(
                    "未配置 LLM API Key（DEEPSEEK_API_KEY），请先在「API 配置」页填写后再使用一键入库。"
                )
            self._llm = DeepSeekClient(
                key.get_secret_value().strip(),
                base_url=self._settings.deepseek_base_url,
                model=self._settings.deepseek_model,
                thinking=self._settings.deepseek_thinking,
            )
        return self._llm

    def _ensure_search(self) -> SearchDiscoveryService:
        if self._search_service is None:
            from app.integrations.search.bocha_web_search import BochaWebSearchProvider

            key = self._settings.bocha_api_key
            provider = BochaWebSearchProvider(
                api_key=key.get_secret_value().strip() if key and key.get_secret_value().strip() else None
            )
            self._search_service = SearchDiscoveryService(self._db, self._settings, provider)
        return self._search_service

    def _ensure_geocoder(self) -> GeocodingService:
        if self._geocoder is None:
            key = self._settings.amap_web_service_api_key
            self._geocoder = GeocodingService(
                key.get_secret_value().strip() if key and key.get_secret_value().strip() else None
            )
        return self._geocoder

    # ---------- 编排入口 ----------

    def intake(self, raw_input: str) -> IntakeOutcome:
        text = (raw_input or "").strip()
        if len(text) < 2:
            raise LandmarkIntakeError("请输入「作品名 + 地标名」，例如：黑神话悟空 小西天。")
        if len(text) > 500:
            raise LandmarkIntakeError("输入过长，请精简到 500 字以内。")

        llm = self._ensure_llm()
        steps: list[IntakeStep] = []
        warnings: list[str] = []

        # 1) 解析意图
        try:
            parsed = llm.generate_json(
                [
                    {"role": "system", "content": PARSE_SYSTEM_PROMPT},
                    {"role": "user", "content": f"用户输入：{text}"},
                ]
            )
        except Exception as exc:  # DeepSeekClientError / Configuration
            raise LandmarkIntakeUnavailable(f"AI 分析失败：{exc}") from exc
        ip_type = str(parsed.get("ip_type") or "").strip()
        try:
            ip_type_enum = IPType(ip_type)
        except ValueError as exc:
            raise LandmarkIntakeError(
                f"无法识别作品类型（得到：{ip_type or '空'}）。请确认输入的是书名/游戏名/影视剧名。"
            ) from exc
        work_title = str(parsed.get("work_title") or "").strip()
        landmark_name = str(parsed.get("landmark_name") or "").strip()
        aliases = str(parsed.get("aliases") or "").strip() or None
        landmark_kind = str(parsed.get("landmark_kind") or "").strip() or None
        if not work_title:
            raise LandmarkIntakeError("无法从输入中识别作品名，请写明书名/游戏名/影视剧名。")
        notes = str(parsed.get("notes") or "").strip()
        if not landmark_name:
            raise LandmarkIntakeError("无法确定地标名，请补充要入库的地标。")
        if "自动选择" in notes:
            warnings.append(f"输入未指明地标，AI 已自动选择：{landmark_name}（{notes}）。")
        steps.append(IntakeStep("parse", "ok", f"{work_title} × {landmark_name}"))

        # 2) 联网检索（可选）
        references: list[dict[str, str]] = []
        search_run_id: int | None = None
        try:
            search = self._ensure_search()
            search_run = search.discover(
                "一键入库资料检索：{work} × {landmark}",
                f"{work_title} {landmark_name} 现实地点 取景地 原型",
            )
            search_run_id = search_run.id
            references = [
                {
                    "title": record.title,
                    "url": record.url,
                    "snippet": (record.snippet or "")[:300],
                }
                for record in search_run.references
            ][:8]
            steps.append(
                IntakeStep(
                    "research",
                    "ok" if references else "skipped",
                    f"检索返回 {len(references)} 条参考" if references else "检索无结果",
                )
            )
            if not references:
                warnings.append("联网检索没有返回可用参考，来源可信度较低，审核发布前请人工核实。")
        except Exception as exc:
            steps.append(IntakeStep("research", "skipped", str(exc)))
            warnings.append(
                "联网检索不可用（未配置 BOCHA_API_KEY 或调用失败），来源未经联网核实，审核发布前请人工确认。"
            )

        # 3) 生成候选条目
        try:
            payload = llm.generate_json(
                [
                    {"role": "system", "content": COMPOSE_SYSTEM_PROMPT},
                    {"role": "user", "content": self._compose_user_prompt(work_title, landmark_name, references)},
                ]
            )
        except Exception as exc:
            raise LandmarkIntakeError(f"AI 生成条目失败：{exc}") from exc

        final_work = str(payload.get("work_title") or "").strip() or work_title
        final_landmark = str(payload.get("landmark_name") or "").strip() or landmark_name
        description = str(payload.get("description") or "").strip()
        if len(description) < 80:
            raise LandmarkIntakeError("AI 生成的简介过短，未达到三段式要求，请重试一次。")

        source_url = str(payload.get("source_url") or "").strip()
        if references:
            allowed = {item["url"] for item in references}
            if source_url not in allowed:
                source_url = references[0]["url"]
                warnings.append("模型选择的来源不在检索结果中，已替换为检索结果第一条。")
        elif not source_url.lower().startswith(("http://", "https://")):
            raise LandmarkIntakeError("AI 未给出可用的来源链接，请重试或先配置博查搜索 Key。")
        if not references:
            warnings.append("条目来源未经联网核实，请打开来源链接确认内容后再审核发布。")

        accessed_at = datetime.now(UTC)
        try:
            row = CandidateRow(
                ip_type=ip_type_enum,
                work_title=final_work,
                aliases=aliases,
                landmark_name=final_landmark,
                country_code=str(payload.get("country_code") or "").strip() or "CN",
                country_name=str(payload.get("country_name") or "").strip() or "中国",
                province_name=self._clean(payload.get("province_name")),
                city_name=self._clean(payload.get("city_name")),
                district_name=self._clean(payload.get("district_name")),
                normalized_address=str(payload.get("normalized_address") or "").strip(),
                description=description,
                transit_text=self._clean(payload.get("transit_text")),
                landmark_kind=landmark_kind or self._clean(payload.get("landmark_kind")),
                source_url=source_url,
                source_title=self._clean(payload.get("source_title")),
                source_publisher=self._clean(payload.get("source_publisher")),
                source_type=str(payload.get("source_type") or "").strip() or "other",
                accessed_at=accessed_at,
            )
        except ValidationError as exc:
            message = "; ".join(f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}" for error in exc.errors())
            raise LandmarkIntakeError(f"生成的条目字段校验失败：{message}") from exc
        steps.append(IntakeStep("compose", "ok", f"地址：{row.normalized_address}"))

        # 4) 地理编码（失败留空，绝不编造）
        try:
            coords = self._ensure_geocoder().geocode(row.country_code, row.normalized_address, row.city_name)
        except Exception as exc:
            coords = None
            warnings.append(f"坐标解析服务调用失败：{exc}")
        if coords is not None:
            row.latitude, row.longitude = coords
            steps.append(IntakeStep("ground", "ok", f"坐标 {coords[0]:.6f},{coords[1]:.6f}"))
        else:
            steps.append(IntakeStep("ground", "skipped", "未能解析出坐标"))
            warnings.append("未能解析出坐标（已留空），审核发布前请人工补全。")

        # 5) 入库为候选
        try:
            landmark = LandmarkImportService(self._db).create_candidate(row)
        except ValueError as exc:
            if "Duplicate" in str(exc):
                raise LandmarkIntakeDuplicate(
                    "已存在相同「作品 + 地标名 + 地址」的条目，无需重复入库。"
                ) from exc
            raise LandmarkIntakeError(str(exc)) from exc
        self._db.commit()
        steps.append(IntakeStep("persist", "ok", f"landmark #{landmark.id}"))

        return IntakeOutcome(
            landmark_id=landmark.id,
            work_title=final_work,
            ip_type=ip_type_enum.value,
            landmark_name=final_landmark,
            address=row.normalized_address,
            latitude=row.latitude,
            longitude=row.longitude,
            description=description,
            source_url=source_url,
            warnings=warnings,
            steps=steps,
            search_run_id=search_run_id,
        )

    # ---------- 内部工具 ----------

    @staticmethod
    def _clean(value: object) -> str | None:
        text = str(value or "").strip()
        return text or None

    @staticmethod
    def _compose_user_prompt(work_title: str, landmark_name: str, references: list[dict[str, str]]) -> str:
        lines = [f"作品：{work_title}", f"地标：{landmark_name}"]
        if references:
            lines.append("联网检索参考（source_url 只能从这里逐字选择）：")
            for index, item in enumerate(references, start=1):
                lines.append(f"{index}. 标题：{item['title']}｜URL：{item['url']}｜摘要：{item['snippet']}")
        else:
            lines.append("（本次没有联网检索参考，请按系统提示的兜底规则给出来源。）")
        return "\n".join(lines)
