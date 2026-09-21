"""地标相册编辑 API：登录门槛、贡献者权限、上传/找图/删除/提交的错误映射。"""

import pytest

from app.api.album import get_album_editor
from app.core.auth import create_access_token
from app.models.contribution import LandmarkContribution
from app.models.enums import MembershipTier
from app.services.landmark_album_editor import (
    AlbumEditorError,
    StagedPhoto,
    StagingNotFoundError,
)


class StubEditor:
    def __init__(self):
        self.deleted = []
        self.submitted = None
        self.download_error = None

    def editor_snapshot(self, landmark_id):
        return {
            "landmark": {"id": landmark_id, "name": "应县木塔", "ip_type": "game", "work_title": "黑神话：悟空", "city": "朔州市"},
            "album_key": "game:应县木塔",
            "published": [{"kind": "published", "file": "game/existing/commons-01.jpg", "url": "/contributions/landmark-albums/images/game/existing/commons-01.jpg", "alt": "旧图", "caption": None, "credit": None, "license": "CC BY 4.0", "source_url": None}],
            "staged": [],
        }

    def save_upload(self, landmark_id, filename, content, content_type, kind="upload"):
        return StagedPhoto(kind=kind, file=f"{kind}-abc123.png", url=f"/staging/landmark-albums/{landmark_id}/{kind}-abc123.png", alt="应县木塔实景", license="用户自传，自行确认版权")

    def list_staged(self, landmark_id):
        return ()

    def delete_staged(self, landmark_id, file):
        if file == "missing.png":
            raise StagingNotFoundError("暂存图片不存在或已被删除。")
        self.deleted.append(file)

    def ai_download(self, landmark_id):
        if self.download_error:
            raise self.download_error
        return type("O", (), {"saved": (), "failures": ({"url": "https://x/y.jpg", "reason": "下载失败"},), "queries": ["应县木塔 实景"], "notices": []})()

    def submit(self, landmark_id, photos):
        self.submitted = photos
        return {"album_key": "game:应县木塔", "published_count": len(photos), "added_count": 1, "removed_count": 0}


@pytest.fixture
def contributor_context(db_session):
    """真实地标 + 贡献归属 + 贡献者登录头。"""
    from tests.factories import create_landmark, create_member

    member = create_member(db_session, MembershipTier.FREE)
    landmark = create_landmark(db_session, published=False, landmark_name="应县木塔")
    db_session.add(LandmarkContribution(
        landmark_id=landmark.id, contributor_name=member.username, contributor_user_id=member.id,
    ))
    db_session.commit()
    headers = {"Authorization": f"Bearer {create_access_token(member.id)}"}
    return headers, landmark.id


def test_editor_endpoints_require_login(client):
    assert client.get("/api/v1/landmarks/1/album/editor").status_code == 401
    assert client.post("/api/v1/landmarks/1/album/editor/uploads").status_code == 401
    assert client.post("/api/v1/landmarks/1/album/editor/ai-download").status_code == 401
    assert client.delete("/api/v1/landmarks/1/album/editor/staged/x.png").status_code == 401
    assert client.post("/api/v1/landmarks/1/album/submit", json={"photos": []}).status_code == 401


def test_editor_snapshot_and_upload(client, app, db_session, contributor_context):
    stub = StubEditor()
    app.dependency_overrides[get_album_editor] = lambda: stub
    headers, landmark_id = contributor_context

    snapshot = client.get(f"/api/v1/landmarks/{landmark_id}/album/editor", headers=headers)
    assert snapshot.status_code == 200
    body = snapshot.json()
    assert body["album_key"] == "game:应县木塔"
    assert body["published"][0]["kind"] == "published"

    upload = client.post(
        f"/api/v1/landmarks/{landmark_id}/album/editor/uploads",
        headers=headers,
        files=[("files", ("a.png", b"fake", "image/png")), ("files", ("b.png", b"fake", "image/png"))],
    )
    assert upload.status_code == 200
    data = upload.json()
    assert len(data["saved"]) == 2
    assert data["saved"][0]["kind"] == "upload"

    deleted = client.delete(f"/api/v1/landmarks/{landmark_id}/album/editor/staged/upload-abc.png", headers=headers)
    assert deleted.status_code == 200
    assert stub.deleted == ["upload-abc.png"]

    missing = client.delete(f"/api/v1/landmarks/{landmark_id}/album/editor/staged/missing.png", headers=headers)
    assert missing.status_code == 404


def test_non_contributor_member_gets_403(client, app, db_session):
    from tests.factories import create_landmark, create_member

    stub = StubEditor()
    app.dependency_overrides[get_album_editor] = lambda: stub
    member = create_member(db_session, MembershipTier.FREE)
    landmark = create_landmark(db_session, published=False, landmark_name="别人的地标")
    db_session.commit()
    headers = {"Authorization": f"Bearer {create_access_token(member.id)}"}

    response = client.get(f"/api/v1/landmarks/{landmark.id}/album/editor", headers=headers)
    assert response.status_code == 403
    assert "贡献者" in response.json()["detail"]


def test_upload_rejects_unsupported_type_with_422(client, app, db_session, contributor_context):
    class RejectingStub(StubEditor):
        def save_upload(self, landmark_id, filename, content, content_type, kind="upload"):
            raise AlbumEditorError("仅支持 JPG / PNG / WebP / AVIF 格式的图片。")

    app.dependency_overrides[get_album_editor] = lambda: RejectingStub()
    headers, landmark_id = contributor_context
    response = client.post(
        f"/api/v1/landmarks/{landmark_id}/album/editor/uploads",
        headers=headers,
        files=[("files", ("a.gif", b"fake", "image/gif"))],
    )
    assert response.status_code == 422
    assert "仅支持" in response.json()["detail"]


def test_ai_download_reports_failures_and_maps_unconfigured_to_503(client, app, db_session, contributor_context):
    stub = StubEditor()
    app.dependency_overrides[get_album_editor] = lambda: stub
    headers, landmark_id = contributor_context

    ok = client.post(f"/api/v1/landmarks/{landmark_id}/album/editor/ai-download", headers=headers)
    assert ok.status_code == 200
    assert ok.json()["failures"][0]["reason"] == "下载失败"
    assert ok.json()["queries"] == ["应县木塔 实景"]

    stub.download_error = AlbumEditorError("未配置博查搜索 Key（BOCHA_API_KEY），无法 AI 找图。")
    failed = client.post(f"/api/v1/landmarks/{landmark_id}/album/editor/ai-download", headers=headers)
    assert failed.status_code == 503


def test_submit_returns_result_and_passes_photos(client, app, db_session, contributor_context):
    stub = StubEditor()
    app.dependency_overrides[get_album_editor] = lambda: stub
    headers, landmark_id = contributor_context
    payload = {
        "photos": [
            {"kind": "published", "file": "game/existing/commons-01.jpg", "alt": "旧图"},
            {"kind": "ai", "file": "ai-abc.png", "alt": "AI 图", "license": "网络检索图片，版权待确认", "source_url": "https://example.org/a"},
        ]
    }
    response = client.post(f"/api/v1/landmarks/{landmark_id}/album/submit", json=payload, headers=headers)

    assert response.status_code == 200
    assert response.json()["published_count"] == 2
    assert stub.submitted[1]["file"] == "ai-abc.png"


def test_album_edit_page_renders(client, db_session):
    from tests.factories import create_landmark

    landmark = create_landmark(db_session, published=False, landmark_name="应县木塔")
    response = client.get(f"/landmarks/{landmark.id}/album/edit")
    assert response.status_code == 200
    assert "相册管理" in response.text
    assert "AI 找图" in response.text
