"""相册键迁移：``<ip_type>:<地标名称>`` → ``landmark:<landmark_id>``。

默认只读 dry-run（不改 manifest、不改数据库），输出映射、缺失与多义清单。
只有唯一匹配才会被自动迁移；同名多义一律留给人裁定。

用法：
    .venv\\Scripts\\python.exe scripts\\migrate_album_keys.py                 # dry-run，打印报告
    .venv\\Scripts\\python.exe scripts\\migrate_album_keys.py --json out.json # 报告写入文件
    .venv\\Scripts\\python.exe scripts\\migrate_album_keys.py --apply --backup-dir backups
        ↑ 需用户明确授权后才可执行；先备份 manifest，再逐键迁移，失败不破坏原文件。

正式数据迁移未获授权时，请只运行 dry-run 并把报告交给用户决定。
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine, select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.models.enums import IPType  # noqa: E402
from app.models.ip_work import IPWork  # noqa: E402
from app.models.landmark import Landmark  # noqa: E402
from app.services.landmark_albums import ALBUM_ROOT, album_key  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = PROJECT_ROOT / ALBUM_ROOT / "manifest.json"


def _load_albums() -> dict:
    if not MANIFEST_PATH.exists():
        return {}
    raw = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    albums = raw.get("albums") if isinstance(raw, dict) else None
    return albums if isinstance(albums, dict) else {}


def _legacy_candidates(session: Session) -> dict[tuple[str, str], list[int]]:
    rows = session.execute(
        select(IPWork.ip_type, Landmark.name, Landmark.id)
        .join(Landmark, Landmark.ip_work_id == IPWork.id)
        .order_by(Landmark.id)
    ).all()
    grouped: dict[tuple[str, str], list[int]] = defaultdict(list)
    for ip_type, name, landmark_id in rows:
        value = ip_type.value if isinstance(ip_type, IPType) else str(ip_type)
        grouped[(value, name)].append(landmark_id)
    return grouped


def build_plan(albums: dict, candidates: dict[tuple[str, str], list[int]]) -> dict:
    plan: dict[str, object] = {"migrate": [], "ambiguous": [], "unmatched": [], "already_migrated": [], "collisions": []}
    targets: dict[str, list[str]] = defaultdict(list)

    for key, entries in albums.items():
        if key.startswith("landmark:"):
            continue
        ip_type, separator, name = key.partition(":")
        if not separator:
            plan["unmatched"].append({"key": key, "reason": "键格式不是 <ip_type>:<名称>"})
            continue
        matches = candidates.get((ip_type, name), [])
        if len(matches) == 1:
            landmark_id = matches[0]
            target = album_key(landmark_id)
            targets[target].append(key)
            if target in albums:
                plan["already_migrated"].append({"key": key, "target": target, "reason": "目标键已存在，跳过"})
                continue
            plan["migrate"].append({"key": key, "target": target, "landmark_id": landmark_id, "photos": len(entries or [])})
        elif len(matches) > 1:
            plan["ambiguous"].append({"key": key, "landmark_ids": matches})
        else:
            plan["unmatched"].append({"key": key, "reason": "数据库中没有同类型同名的地标"})

    for target, keys in targets.items():
        if len(keys) > 1:
            plan["collisions"].append({"target": target, "keys": keys})
    return plan


def apply_plan(plan: dict, backup_dir: Path | None) -> dict:
    albums = _load_albums()
    if backup_dir is not None:
        backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
        shutil.copy2(MANIFEST_PATH, backup_dir / f"manifest-{stamp}.json")

    migrated = []
    for item in plan["migrate"]:
        source_key, target_key = item["key"], item["target"]
        if source_key not in albums or target_key in albums:
            continue
        albums[target_key] = albums.pop(source_key)
        migrated.append({"from": source_key, "to": target_key})

    if migrated:
        tmp_path = MANIFEST_PATH.with_suffix(".json.tmp")
        payload = {"schema_version": 1, "albums": albums}
        tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        tmp_path.replace(MANIFEST_PATH)
    return {"migrated": migrated, "remaining_albums": len(albums)}


def main() -> int:
    parser = argparse.ArgumentParser(description="相册旧键迁移（默认 dry-run）")
    parser.add_argument("--database-url", default=None, help="默认读取 Settings.database_url")
    parser.add_argument("--json", default=None, help="把报告写入指定文件")
    parser.add_argument("--apply", action="store_true", help="执行迁移（需用户授权）")
    parser.add_argument("--backup-dir", default=None, help="执行迁移前备份 manifest 的目录")
    arguments = parser.parse_args()

    engine = create_engine(arguments.database_url or get_settings().database_url)
    try:
        with Session(engine) as session:
            plan = build_plan(_load_albums(), _legacy_candidates(session))
    finally:
        engine.dispose()

    report: dict[str, object] = {
        "mode": "apply" if arguments.apply else "dry-run",
        "manifest": str(MANIFEST_PATH.relative_to(PROJECT_ROOT)),
        **plan,
    }
    if arguments.apply:
        if not arguments.backup_dir:
            print("拒绝执行：--apply 必须同时提供 --backup-dir 备份目录。", file=sys.stderr)
            return 2
        report["applied"] = apply_plan(plan, Path(arguments.backup_dir))

    text = json.dumps(report, ensure_ascii=False, indent=2)
    if arguments.json:
        Path(arguments.json).write_text(text + "\n", encoding="utf-8")
    print(text)
    print(
        f"\n可迁移 {len(report['migrate'])} 条；多义 {len(report['ambiguous'])} 条；"
        f"未匹配 {len(report['unmatched'])} 条；已迁移 {len(report['already_migrated'])} 条。",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
