"""启动隔离服务并运行真实浏览器冒烟。

- 数据库：临时 SQLite，由 Alembic 从空库建表（不碰正式库）。
- 数据：合成用户/作品/地标/贡献记录。
- 服务：独立 uvicorn 端口，只绑定 127.0.0.1；结束后自动关闭。
- 外部服务：清空所有第三方凭据环境变量，测试地图瓦片使用本地占位地址。

用法：
    .venv\\Scripts\\python.exe scripts\\run_browser_smoke.py --out 测试证据\\项目改进实施20261022\\browser
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

NODE = Path("C:/Users/Administrator/.workbuddy/binaries/node/versions/22.22.2-6/node.exe")
NODE_MODULES = Path("C:/Users/Administrator/.workbuddy/binaries/node/workspace/node_modules")
SMOKE_SCRIPT = PROJECT_ROOT / "tests" / "browser" / "smoke.mjs"

SMOKE_USER = "smoke_user"
SMOKE_PASSWORD = "smoke-password-123"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _prepare_database(database_url: str) -> dict[str, int]:
    """在隔离库上跑迁移并写入合成数据。"""
    env = {**os.environ, "DATABASE_URL": database_url}
    for key in ("DEEPSEEK_API_KEY", "AMAP_WEB_SERVICE_API_KEY", "MEITUAN_HT_TOKEN", "MEITUAN_TRAVEL_TOKEN"):
        env[key] = ""
    env["DEV_BYPASS_AUTH"] = "false"
    subprocess.run(
        [str(PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"), "-m", "alembic", "upgrade", "head"],
        cwd=PROJECT_ROOT, env=env, check=True, capture_output=True,
    )

    os.environ.update({key: env[key] for key in ("DEEPSEEK_API_KEY", "AMAP_WEB_SERVICE_API_KEY", "MEITUAN_HT_TOKEN", "MEITUAN_TRAVEL_TOKEN", "DEV_BYPASS_AUTH")})
    os.environ["DATABASE_URL"] = database_url
    from app.core.config import get_settings

    get_settings.cache_clear()

    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from app.core.password import hash_password
    from app.models.contribution import LandmarkContribution
    from app.models.enums import IPType, MembershipTier, PublicationStatus, UserRole, VerificationStatus
    from app.models.ip_work import IPWork
    from app.models.landmark import Landmark
    from app.models.location import Location
    from app.models.membership import Membership
    from app.models.review import LandmarkReview
    from app.models.source import LandmarkSource, Source
    from app.models.user import User

    engine = create_engine(database_url)
    now = datetime.now(UTC)
    with Session(engine) as session:
        user = User(
            username=SMOKE_USER,
            email="smoke@example.org",
            password_hash=hash_password(SMOKE_PASSWORD),
            role=UserRole.LEVEL1.value,
        )
        session.add(user)
        session.flush()
        session.add(Membership(user_id=user.id, tier=MembershipTier.FREE))

        admin = User(username="smoke_admin", email="smoke-admin@example.org", password_hash=hash_password("admin-password-123"), role=UserRole.ADMIN.value, is_admin=True)
        session.add(admin)

        specimens = [
            ("黑神话：悟空", IPType.GAME, "应县木塔", "山西省", "朔州市", 39.57, 113.17),
            ("黑神话：悟空", IPType.GAME, "小西天", "山西省", "临汾市", 36.72, 111.19),
            ("黑神话：悟空", IPType.GAME, "玉皇庙", "山西省", "晋城市", 35.49, 112.85),
            ("边城", IPType.LITERATURE, "边城茶峒古镇", "湖南省", "湘西州", 28.42, 109.45),
            ("情书", IPType.SCREEN, "小樽运河", "北海道", "小樽市", 43.19, 141.00),
            ("狂飙", IPType.SCREEN, "长堤历史文化街区", "广东省", "江门市", 22.58, 113.08),
        ]
        works: dict[str, IPWork] = {}
        landmark_ids: list[int] = []
        for index, (work_title, ip_type, name, province, city, lat, lng) in enumerate(specimens, start=1):
            work = works.get(work_title)
            if work is None:
                work = IPWork(title=work_title, aliases=f"{work_title}别名", ip_type=ip_type, status=PublicationStatus.PUBLISHED)
                session.add(work)
                session.flush()
                works[work_title] = work
            location = Location(
                country_code="CN", country_name="中国", province_name=province, city_name=city,
                normalized_address=f"{province}{city}{name}", latitude=lat, longitude=lng,
            )
            landmark = Landmark(
                ip_work=work, location=location, name=name,
                description=f"{name}的合成简介，用于浏览器冒烟测试。",
                transit_text="乘公共交通到站后步行可达。",
                verification_status=VerificationStatus.VERIFIED, published_at=now,
            )
            session.add(landmark)
            session.flush()
            source = Source(url=f"https://example.org/smoke/{index}", title="冒烟测试来源", publisher="smoke", source_type="official", accessed_at=now)
            session.add(source)
            session.flush()
            session.add(LandmarkSource(landmark_id=landmark.id, source_id=source.id, claim_scope="verification"))
            landmark_ids.append(landmark.id)
            if index == 1:
                session.add(LandmarkContribution(landmark_id=landmark.id, contributor_name=SMOKE_USER, contributor_user_id=user.id))
                session.add(LandmarkReview(landmark_id=landmark.id, decision=VerificationStatus.VERIFIED, reason="资料完整，核验通过。", reviewer_name="smoke_admin"))

        # 60 条合成地标：专门用于验证「搜索超过一页仍可访问后续结果」与「选择器超过 50 条可翻页」
        bulk_work = IPWork(title="测试合集", ip_type=IPType.LITERATURE, status=PublicationStatus.PUBLISHED)
        session.add(bulk_work)
        session.flush()
        for index in range(1, 61):
            bulk_location = Location(
                country_code="CN", country_name="中国", province_name="测试省", city_name="测试市",
                normalized_address=f"测试省测试市测试地标{index:02d}",
                latitude=30.0 + index / 1000, longitude=110.0 + index / 1000,
            )
            bulk_landmark = Landmark(
                ip_work=bulk_work, location=bulk_location, name=f"测试地标{index:02d}",
                description=f"第 {index:02d} 条合成地标，用于分页与选择器回归。",
                transit_text="合成数据，不含真实交通信息。",
                # 发布时间早于演示地标，避免分页用的合成数据占满首页「精选地标」
                verification_status=VerificationStatus.VERIFIED, published_at=now - timedelta(days=30),
            )
            session.add(bulk_landmark)
            session.flush()
            bulk_source = Source(
                url=f"https://example.org/bulk/{index}", title="分页回归来源", publisher="smoke",
                source_type="official", accessed_at=now,
            )
            session.add(bulk_source)
            session.flush()
            session.add(LandmarkSource(landmark_id=bulk_landmark.id, source_id=bulk_source.id, claim_scope="verification"))

        # 一条待审核的候选，用于「我的贡献」展示审核反馈
        candidate = Landmark(
            ip_work=works["黑神话：悟空"],
            location=Location(country_code="CN", country_name="中国", province_name="山西省", city_name="大同市", normalized_address="山西省大同市云冈石窟"),
            name="云冈石窟",
            description="候选条目简介，等待审核。",
            verification_status=VerificationStatus.CANDIDATE,
        )
        session.add(candidate)
        session.flush()
        session.add(LandmarkContribution(landmark_id=candidate.id, contributor_name=SMOKE_USER, contributor_user_id=user.id))
        session.add(LandmarkReview(landmark_id=candidate.id, decision=VerificationStatus.CANDIDATE, reason="已收到，等待来源补充核对。", reviewer_name=SMOKE_USER))
        session.commit()
        first_landmark_id = landmark_ids[0]

    engine.dispose()
    return {"first_landmark_id": first_landmark_id, "landmark_count": len(landmark_ids)}


def _wait_for_health(base_url: str, process: subprocess.Popen, timeout: float = 40.0) -> None:
    import urllib.error
    import urllib.request

    deadline = time.time() + timeout
    while time.time() < deadline:
        if process.poll() is not None:
            raise RuntimeError("服务进程提前退出")
        try:
            with urllib.request.urlopen(f"{base_url}/health/live", timeout=2) as response:
                if response.status == 200:
                    return
        except (urllib.error.URLError, TimeoutError):
            time.sleep(0.4)
    raise RuntimeError("服务未在预期时间内就绪")


def main() -> int:
    parser = argparse.ArgumentParser(description="隔离服务 + 真实浏览器冒烟")
    parser.add_argument("--out", default=str(PROJECT_ROOT / "测试证据" / "项目改进实施20261022" / "browser"))
    arguments = parser.parse_args()
    out_dir = Path(arguments.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    workdir = Path(tempfile.mkdtemp(prefix="worldmark-browser-"))
    database_path = workdir / "browser.db"
    database_url = f"sqlite+pysqlite:///{database_path}"
    seeded = _prepare_database(database_url)

    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"
    env = {
        **os.environ,
        "DATABASE_URL": database_url,
        "DEV_BYPASS_AUTH": "false",
        "APP_ENV": "development",
        "MAP_TILE_URL": f"{base_url}/static/favicon.svg",  # 本地占位瓦片，不访问第三方
    }
    for key in ("DEEPSEEK_API_KEY", "AMAP_WEB_SERVICE_API_KEY", "MEITUAN_HT_TOKEN", "MEITUAN_TRAVEL_TOKEN"):
        env[key] = ""

    log_path = workdir / "server.log"
    with log_path.open("w", encoding="utf-8") as log_file:
        server = subprocess.Popen(
            [str(PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"), "-m", "uvicorn", "app.main:app",
             "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"],
            cwd=PROJECT_ROOT, env=env, stdout=log_file, stderr=subprocess.STDOUT,
        )
        try:
            _wait_for_health(base_url, server)
            command = [
                str(NODE), str(SMOKE_SCRIPT),
                "--base-url", base_url,
                "--out", str(out_dir),
                "--username", SMOKE_USER,
                "--password", SMOKE_PASSWORD,
                "--landmark-id", str(seeded["first_landmark_id"]),
            ]
            completed = subprocess.run(
                command, cwd=PROJECT_ROOT,
                env={**os.environ, "NODE_PATH": str(NODE_MODULES), "PLAYWRIGHT_MODULE": str(NODE_MODULES / "playwright")},
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300,
            )
            print(completed.stdout)
            if completed.stderr.strip():
                print(completed.stderr, file=sys.stderr)
            summary = {
                "exit_code": completed.returncode,
                "database": str(database_path),
                "landmark_count": seeded["landmark_count"],
                "server_log_tail": log_path.read_text(encoding="utf-8", errors="replace")[-2000:],
                "runner": "tests/browser/smoke.mjs",
            }
            (out_dir / "browser-smoke-runner.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
            return completed.returncode
        finally:
            server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()


if __name__ == "__main__":
    raise SystemExit(main())
