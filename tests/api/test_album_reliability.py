"""阶段03 回归：相册稳定归属、暂存鉴权、真实图片校验、提交一致性与冲突。"""

from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest
from PIL import Image

from app.core.config import get_settings
from app.core.auth import create_access_token
from app.models.contribution import LandmarkContribution
from app.models.enums import MembershipTier, UserRole
from app.services.landmark_album_editor import (
    AlbumConflictError,
    AlbumEditorError,
    LandmarkAlbumEditorService,
)
from app.services.landmark_albums import LandmarkAlbumService, album_key, legacy_album_key
from tests.factories import create_landmark, create_member
from tests.images import CORRUPT_IMAGE_BYTES, REAL_JPEG_BYTES, REAL_PNG_BYTES


def _album_root(project_root: Path) -> Path:
    return project_root / "data" / "contributions" / "landmark_albums"


def _write_manifest(project_root: Path, albums: dict) -> None:
    root = _album_root(project_root)
    (root / "images").mkdir(parents=True, exist_ok=True)
    (root / "manifest.json").write_text(
        json.dumps({"schema_version": 1, "albums": albums}, ensure_ascii=False), encoding="utf-8"
    )


def _add_image(project_root: Path, relative: str, content: bytes = REAL_JPEG_BYTES) -> None:
    target = _album_root(project_root) / "images" / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)


@pytest.fixture()
def project_root(tmp_path) -> Path:
    _write_manifest(tmp_path, {})
    return tmp_path


@pytest.fixture()
def editor(db_session, project_root) -> LandmarkAlbumEditorService:
    return LandmarkAlbumEditorService(db_session, project_root, settings=get_settings())


# ------------------------------------------------------- B08 稳定归属与改名


def test_renaming_landmark_keeps_its_photos(db_session, project_root):
    landmark = create_landmark(db_session, landmark_name="应县木塔", published=False)
    _add_image(project_root, "game/yingxian/photo.jpg")
    _write_manifest(project_root, {album_key(landmark.id): [
        {"file": "game/yingxian/photo.jpg", "alt": "木塔外观", "license": "CC BY 4.0"}
    ]})

    landmark.name = "应县木塔（释迦塔）"
    db_session.commit()

    photos = LandmarkAlbumService(project_root).get_photos(landmark.id)
    assert len(photos) == 1
    assert photos[0].alt == "木塔外观"


def test_same_name_landmarks_do_not_share_photos(db_session, project_root):
    first = create_landmark(db_session, landmark_name="同名地标", published=False)
    second = create_landmark(db_session, work_title="另一部作品", landmark_name="同名地标", published=False)
    _add_image(project_root, "game/first/a.jpg")
    _add_image(project_root, "game/second/b.jpg")
    _write_manifest(project_root, {
        album_key(first.id): [{"file": "game/first/a.jpg", "alt": "甲"}],
        album_key(second.id): [{"file": "game/second/b.jpg", "alt": "乙"}],
    })

    service = LandmarkAlbumService(project_root)
    assert [photo.alt for photo in service.get_photos(first.id)] == ["甲"]
    assert [photo.alt for photo in service.get_photos(second.id)] == ["乙"]


def test_editor_snapshot_shows_legacy_album_once_then_writes_new_key(db_session, project_root):
    landmark = create_landmark(db_session, landmark_name="历史地标", published=False)
    _add_image(project_root, "game/legacy/old.jpg")
    _write_manifest(project_root, {
        legacy_album_key("game", "历史地标"): [{"file": "game/legacy/old.jpg", "alt": "旧图"}]
    })
    editor = LandmarkAlbumEditorService(db_session, project_root, settings=get_settings())

    snapshot = editor.editor_snapshot(landmark.id)
    assert snapshot["legacy_album_key"] == legacy_album_key("game", "历史地标")
    assert [item["file"] for item in snapshot["published"]] == ["game/legacy/old.jpg"]

    upload = editor.save_upload(landmark.id, "new.png", REAL_PNG_BYTES, "image/png")
    editor.submit(landmark.id, [
        {"kind": "published", "file": "game/legacy/old.jpg", "alt": "旧图"},
        {"kind": "upload", "file": upload.file, "alt": "新图"},
    ])

    manifest = json.loads((_album_root(project_root) / "manifest.json").read_text(encoding="utf-8"))
    assert album_key(landmark.id) in manifest["albums"]
    assert len(manifest["albums"][album_key(landmark.id)]) == 2
    # 旧键保留（不破坏历史数据），但读取已切到新键
    assert legacy_album_key("game", "历史地标") in manifest["albums"]


# ------------------------------------------------- B09 真实图片校验与边界


def test_pseudo_mime_is_rejected(editor, db_session):
    landmark = create_landmark(db_session, published=False)
    with pytest.raises(AlbumEditorError, match="不一致"):
        editor.save_upload(landmark.id, "fake.jpg", REAL_PNG_BYTES, "image/jpeg")


def test_corrupt_and_truncated_images_are_rejected(editor, db_session):
    landmark = create_landmark(db_session, published=False)
    with pytest.raises(AlbumEditorError, match="无法解码"):
        editor.save_upload(landmark.id, "broken.png", CORRUPT_IMAGE_BYTES, "image/png")


def test_pixel_limit_is_enforced(editor, db_session, monkeypatch):
    from app.services import landmark_album_editor as module

    monkeypatch.setattr(module, "MAX_IMAGE_PIXELS", 4)
    landmark = create_landmark(db_session, published=False)
    with pytest.raises(AlbumEditorError, match="像素过大"):
        editor.save_upload(landmark.id, "big.png", REAL_PNG_BYTES, "image/png")


def test_real_formats_are_accepted(editor, db_session):
    landmark = create_landmark(db_session, published=False)
    for name, content, mime in (
        ("a.png", REAL_PNG_BYTES, "image/png"),
        ("b.jpg", REAL_JPEG_BYTES, "image/jpeg"),
    ):
        photo = editor.save_upload(landmark.id, name, content, mime)
        assert photo.file.startswith("upload-")


# ------------------------------------------- R05 提交一致性与乐观并发检查


def test_stale_revision_is_rejected(db_session, project_root):
    landmark = create_landmark(db_session, published=False)
    _add_image(project_root, "game/x/a.jpg")
    _write_manifest(project_root, {album_key(landmark.id): [{"file": "game/x/a.jpg", "alt": "甲"}]})
    editor = LandmarkAlbumEditorService(db_session, project_root, settings=get_settings())

    stale = editor.editor_snapshot(landmark.id)["revision"]
    upload = editor.save_upload(landmark.id, "n.png", REAL_PNG_BYTES, "image/png")
    editor.submit(landmark.id, [
        {"kind": "published", "file": "game/x/a.jpg", "alt": "甲"},
        {"kind": "upload", "file": upload.file, "alt": "新"},
    ])

    second = editor.save_upload(landmark.id, "m.png", REAL_PNG_BYTES, "image/png")
    with pytest.raises(AlbumConflictError, match="刷新"):
        editor.submit(
            landmark.id,
            [{"kind": "upload", "file": second.file, "alt": "旧会话提交"}],
            expected_revision=stale,
        )


def test_manifest_write_failure_rolls_back_moved_files(db_session, project_root, monkeypatch):
    landmark = create_landmark(db_session, published=False)
    _add_image(project_root, "game/x/a.jpg")
    _write_manifest(project_root, {album_key(landmark.id): [{"file": "game/x/a.jpg", "alt": "甲"}]})
    editor = LandmarkAlbumEditorService(db_session, project_root, settings=get_settings())
    upload = editor.save_upload(landmark.id, "n.png", REAL_PNG_BYTES, "image/png")

    def explode(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(editor, "_write_album_entries", explode)
    with pytest.raises(OSError):
        editor.submit(landmark.id, [
            {"kind": "published", "file": "game/x/a.jpg", "alt": "甲"},
            {"kind": "upload", "file": upload.file, "alt": "新"},
        ])

    # 暂存文件回滚到暂存区，原相册条目与图片都还在
    assert any(item.file == upload.file for item in editor.list_staged(landmark.id))
    manifest = json.loads((_album_root(project_root) / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["albums"][album_key(landmark.id)] == [{"file": "game/x/a.jpg", "alt": "甲"}]
    assert (_album_root(project_root) / "images" / "game/x/a.jpg").is_file()


def test_concurrent_submissions_on_same_album_only_one_wins(db_session, database_engine, project_root):
    landmark = create_landmark(db_session, published=False)
    _add_image(project_root, "game/x/a.jpg")
    _write_manifest(project_root, {album_key(landmark.id): [{"file": "game/x/a.jpg", "alt": "甲"}]})

    from sqlalchemy.orm import sessionmaker

    factory = sessionmaker(bind=database_engine, autoflush=False, autocommit=False, expire_on_commit=False)
    first = LandmarkAlbumEditorService(factory(), project_root, settings=get_settings())
    second = LandmarkAlbumEditorService(factory(), project_root, settings=get_settings())
    revision = first.editor_snapshot(landmark.id)["revision"]
    upload_a = first.save_upload(landmark.id, "a.png", REAL_PNG_BYTES, "image/png")
    upload_b = second.save_upload(landmark.id, "b.png", REAL_PNG_BYTES, "image/png")

    results: list[str] = []

    def worker(service, upload):
        try:
            service.submit(
                landmark.id,
                [{"kind": "published", "file": "game/x/a.jpg", "alt": "甲"},
                 {"kind": "upload", "file": upload.file, "alt": "并发提交"}],
                expected_revision=revision,
            )
            results.append("ok")
        except AlbumConflictError:
            results.append("conflict")

    threads = [
        threading.Thread(target=worker, args=(first, upload_a)),
        threading.Thread(target=worker, args=(second, upload_b)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert sorted(results) == ["conflict", "ok"]


# ------------------------------------------- B10 暂存与未发布图片的访问边界


def _headers(user) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


@pytest.fixture()
def isolated_album_root(app, tmp_path, monkeypatch):
    from app.web.album_images import get_project_root

    _write_manifest(tmp_path, {})
    app.dependency_overrides[get_project_root] = lambda: tmp_path
    yield tmp_path
    app.dependency_overrides.pop(get_project_root, None)


def test_staging_images_require_contributor(client, db_session, isolated_album_root):
    contributor = create_member(db_session, MembershipTier.FREE, role=UserRole.LEVEL1.value)
    outsider = create_member(db_session, MembershipTier.FREE, role=UserRole.LEVEL1.value)
    landmark = create_landmark(db_session, landmark_name="暂存地标", published=False)
    db_session.add(LandmarkContribution(
        landmark_id=landmark.id, contributor_name=contributor.username, contributor_user_id=contributor.id,
    ))
    db_session.commit()

    editor = LandmarkAlbumEditorService(db_session, isolated_album_root, settings=get_settings())
    photo = editor.save_upload(landmark.id, "a.png", REAL_PNG_BYTES, "image/png")
    url = f"/staging/landmark-albums/{landmark.id}/{photo.file}"

    assert client.get(url).status_code == 404  # 匿名
    assert client.get(url, headers=_headers(outsider)).status_code == 404
    allowed = client.get(url, headers=_headers(contributor))
    assert allowed.status_code == 200
    assert allowed.headers["cache-control"] == "private, no-store"

    meta = client.get(f"/staging/landmark-albums/{landmark.id}/_meta.json", headers=_headers(contributor))
    assert meta.status_code == 404


def test_unpublished_album_image_is_not_public(client, db_session, isolated_album_root):
    contributor = create_member(db_session, MembershipTier.FREE, role=UserRole.LEVEL1.value)
    landmark = create_landmark(db_session, landmark_name="待审地标", published=False)
    db_session.add(LandmarkContribution(
        landmark_id=landmark.id, contributor_name=contributor.username, contributor_user_id=contributor.id,
    ))
    db_session.commit()
    _add_image(isolated_album_root, "game/pending/a.jpg")
    _write_manifest(isolated_album_root, {album_key(landmark.id): [
        {"file": "game/pending/a.jpg", "alt": "待审图片"}
    ]})
    url = "/contributions/landmark-albums/images/game/pending/a.jpg"

    assert client.get(url).status_code == 404
    # 贡献者可预览自己的待审相册
    assert client.get(url, headers=_headers(contributor)).status_code == 200


def test_published_album_image_becomes_public(client, db_session, isolated_album_root):
    from datetime import UTC, datetime

    from app.models.enums import VerificationStatus

    landmark = create_landmark(db_session, landmark_name="已发布地标", published=False)
    landmark.verification_status = VerificationStatus.VERIFIED
    landmark.published_at = datetime.now(UTC)
    landmark.ip_work.status = "published"
    db_session.commit()
    _add_image(isolated_album_root, "game/live/a.jpg")
    _write_manifest(isolated_album_root, {album_key(landmark.id): [
        {"file": "game/live/a.jpg", "alt": "已发布图片"}
    ]})

    assert client.get("/contributions/landmark-albums/images/game/live/a.jpg").status_code == 200


def test_unreferenced_image_is_not_served(client, isolated_album_root):
    _add_image(isolated_album_root, "game/orphan/a.jpg")
    assert client.get("/contributions/landmark-albums/images/game/orphan/a.jpg").status_code == 404


def test_path_traversal_is_blocked(client, isolated_album_root):
    assert client.get("/contributions/landmark-albums/images/../../.env").status_code == 404


# ------------------------------------------------------------- API 上传边界


def test_upload_rejects_oversized_and_too_many_files(client, db_session, isolated_album_root):
    contributor = create_member(db_session, MembershipTier.FREE, role=UserRole.LEVEL1.value)
    landmark = create_landmark(db_session, landmark_name="上传边界", published=False)
    db_session.add(LandmarkContribution(
        landmark_id=landmark.id, contributor_name=contributor.username, contributor_user_id=contributor.id,
    ))
    db_session.commit()

    big = b"x" * (8 * 1024 * 1024 + 1024)
    response = client.post(
        f"/api/v1/landmarks/{landmark.id}/album/editor/uploads",
        files=[("files", ("big.png", big, "image/png"))],
        headers=_headers(contributor),
    )
    assert response.status_code == 422
    assert "8MB" in response.json()["detail"]

    files = [("files", (f"{index}.png", REAL_PNG_BYTES, "image/png")) for index in range(13)]
    too_many = client.post(
        f"/api/v1/landmarks/{landmark.id}/album/editor/uploads",
        files=files,
        headers=_headers(contributor),
    )
    assert too_many.status_code == 413


def test_submit_conflict_returns_409(client, app, db_session, isolated_album_root):
    from app.api.album import get_album_editor

    contributor = create_member(db_session, MembershipTier.FREE, role=UserRole.LEVEL1.value)
    landmark = create_landmark(db_session, landmark_name="冲突地标", published=False)
    db_session.add(LandmarkContribution(
        landmark_id=landmark.id, contributor_name=contributor.username, contributor_user_id=contributor.id,
    ))
    db_session.commit()

    editor = LandmarkAlbumEditorService(db_session, isolated_album_root, settings=get_settings())
    app.dependency_overrides[get_album_editor] = lambda: editor
    try:
        photo = editor.save_upload(landmark.id, "a.png", REAL_PNG_BYTES, "image/png")

        response = client.post(
            f"/api/v1/landmarks/{landmark.id}/album/submit",
            json={
                "photos": [{"kind": "upload", "file": photo.file, "alt": "新"}],
                "expected_revision": "stale-revision",
            },
            headers=_headers(contributor),
        )
        assert response.status_code == 409
    finally:
        app.dependency_overrides.pop(get_album_editor, None)
