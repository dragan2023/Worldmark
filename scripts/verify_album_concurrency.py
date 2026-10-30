"""相册提交的多进程并发验证（跨进程文件锁 + 版本冲突）。

父进程准备隔离目录与 SQLite，然后起两个真实子进程同时提交同一相册：
应当只有一个成功，另一个得到版本冲突；失败方的暂存文件保持可重试。
再对两个不同地标并发提交，应当两边都成功。
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def _seed(root: Path, landmark_count: int) -> str:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from app.models import Base
    from app.models.enums import IPType, PublicationStatus, VerificationStatus
    from app.models.ip_work import IPWork
    from app.models.landmark import Landmark
    from app.models.location import Location

    database_path = root / "album.db"
    url = f"sqlite+pysqlite:///{database_path}"
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    now = datetime.now(UTC)
    with Session(engine) as session:
        work = IPWork(title="并发验证作品", ip_type=IPType.GAME, status=PublicationStatus.PUBLISHED)
        session.add(work)
        session.flush()
        for index in range(1, landmark_count + 1):
            session.add(
                Landmark(
                    ip_work_id=work.id,
                    location=Location(country_code="CN", country_name="中国", province_name="山西省", city_name="大同市", normalized_address=f"并发地标{index}"),
                    name=f"并发地标{index}",
                    description="并发验证用合成地标。",
                    verification_status=VerificationStatus.VERIFIED,
                    published_at=now,
                )
            )
        session.commit()
    engine.dispose()
    return url


def _editor(database_url: str, root: Path):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from app.core.config import get_settings
    from app.services.landmark_album_editor import LandmarkAlbumEditorService

    engine = create_engine(database_url)
    session = Session(engine)
    return engine, LandmarkAlbumEditorService(session, root, settings=get_settings())


def _staging_file(database_url: str, root: Path, landmark_id: int, name: str) -> str:
    engine, editor = _editor(database_url, root)
    staged = editor.save_upload(landmark_id, name, TINY_PNG, "image/png")
    engine.dispose()
    return staged.file


def _worker(args: argparse.Namespace) -> int:
    from app.services.landmark_album_editor import AlbumConflictError, AlbumEditorError

    engine, editor = _editor(args.database_url, Path(args.root))
    payload = [{"kind": "upload", "file": args.file, "alt": args.label + " 图片", "license": "CC0"}]
    try:
        editor.submit(args.landmark, payload, expected_revision=args.revision)
        print(json.dumps({"worker": args.label, "ok": True}))
    except (AlbumConflictError, AlbumEditorError) as exc:
        print(json.dumps({"worker": args.label, "ok": False, "error": type(exc).__name__, "message": str(exc)}))
    finally:
        engine.dispose()
    return 0


def _spawn(database_url: str, root: Path, landmark_id: int, label: str, revision: str, file_name: str) -> subprocess.Popen:
    command = [
        sys.executable, str(Path(__file__).resolve()), "--worker",
        "--root", str(root), "--database-url", database_url,
        "--landmark", str(landmark_id), "--label", label,
        "--revision", revision, "--file", file_name,
    ]
    return subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--root")
    parser.add_argument("--database-url")
    parser.add_argument("--landmark", type=int)
    parser.add_argument("--label")
    parser.add_argument("--revision")
    parser.add_argument("--file")
    parser.add_argument("--out")
    args = parser.parse_args()
    if args.worker:
        return _worker(args)

    root = Path(tempfile.mkdtemp(prefix="worldmark-album-concurrency-"))
    database_url = _seed(root, landmark_count=2)

    # 场景一：同一相册并发提交
    _, editor = _editor(database_url, root)
    revision = editor.editor_snapshot(1)["revision"]
    file_a = _staging_file(database_url, root, 1, "a.png")
    file_b = _staging_file(database_url, root, 1, "b.png")
    first = _spawn(database_url, root, 1, "A", revision, file_a)
    second = _spawn(database_url, root, 1, "B", revision, file_b)
    outputs = []
    for process in (first, second):
        stdout, stderr = process.communicate(timeout=120)
        outputs.append(json.loads(stdout.strip().splitlines()[-1]) if stdout.strip() else {"ok": False, "raw": stderr[-300:]})

    manifest = json.loads((root / "data/contributions/landmark_albums/manifest.json").read_text(encoding="utf-8"))
    entries = manifest["albums"].get("landmark:1", [])
    images = sorted(p.name for p in (root / "data/contributions/landmark_albums/images").rglob("*") if p.is_file())
    staging_left = sorted(p.name for p in (root / "uploads/landmark_albums/1").glob("*")) if (root / "uploads/landmark_albums/1").exists() else []

    # 场景二：不同地标并发提交（不应互相阻塞或冲突）
    revision_two = editor.editor_snapshot(2)["revision"]
    file_c = _staging_file(database_url, root, 1, "c.png")
    file_d = _staging_file(database_url, root, 2, "d.png")
    third = _spawn(database_url, root, 1, "C", album_revision_lookup(editor, 1), file_c)
    fourth = _spawn(database_url, root, 2, "D", revision_two, file_d)
    outputs_two = []
    for process in (third, fourth):
        stdout, stderr = process.communicate(timeout=120)
        outputs_two.append(json.loads(stdout.strip().splitlines()[-1]) if stdout.strip() else {"ok": False, "raw": stderr[-300:]})

    report = {
        "isolated_root": str(root),
        "same_album": {
            "results": outputs,
            "success_count": sum(1 for item in outputs if item.get("ok")),
            "manifest_entries": len(entries),
            "image_files": images,
            "staging_left": staging_left,
        },
        "different_albums": {
            "results": outputs_two,
            "success_count": sum(1 for item in outputs_two if item.get("ok")),
        },
        "lock_file_present": (root / "data/contributions/landmark_albums/.manifest.lock").exists(),
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    print(text)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    return 0 if report["same_album"]["success_count"] == 1 and report["different_albums"]["success_count"] == 2 else 1


def album_revision_lookup(editor, landmark_id: int) -> str:
    return editor.editor_snapshot(landmark_id)["revision"]


if __name__ == "__main__":
    raise SystemExit(main())
