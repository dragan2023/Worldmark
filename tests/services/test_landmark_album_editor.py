"""地标相册编辑服务：暂存、AI 找图下载、提交落库与 manifest 原子更新。"""

import json

import pytest

from app.core.config import get_settings
from app.models.enums import IPType
from app.services.landmark_album_editor import (
    AlbumEditorError,
    LandmarkAlbumEditorService,
    StagingNotFoundError,
)

PNG_BYTES = b"\x89PNG\r\n\x1a\nfake-png-content"


class FakeProvider:
    def __init__(self, candidates):
        self.candidates = candidates
        self.queries = []

    def search(self, query, count=6):
        self.queries.append(query)
        return type("R", (), {"request_id": "log-1", "candidates": self.candidates})()


class FakeLLM:
    def __init__(self, payloads):
        self.payloads = list(payloads)
        self.prompts = []

    def generate_json(self, messages, **kwargs):
        self.prompts.append(messages[-1]["content"])
        return self.payloads.pop(0)


@pytest.fixture()
def project_root(tmp_path):
    root = tmp_path
    album_root = root / "data" / "contributions" / "landmark_albums"
    existing = album_root / "images" / "game" / "existing-landmark"
    existing.mkdir(parents=True)
    (existing / "commons-01.jpg").write_bytes(b"old-image-bytes")
    manifest = {
        "schema_version": 1,
        "albums": {
            "game:应县木塔": [
                {"file": "game/existing-landmark/commons-01.jpg", "alt": "旧图", "license": "CC BY 4.0", "credit": "某人"}
            ],
            "literature:别的地标": [
                {"file": "literature/other/commons-01.jpg", "alt": "别家"}
            ],
        },
    }
    (album_root / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    return root


@pytest.fixture()
def landmark(db_session):
    from tests.factories import create_landmark

    return create_landmark(db_session, published=False, work_title="黑神话：悟空", landmark_name="应县木塔")


@pytest.fixture()
def editor(db_session, project_root):
    return LandmarkAlbumEditorService(db_session, project_root, settings=get_settings())


def test_save_upload_stores_file_and_lists_staged(editor, landmark, project_root):
    photo = editor.save_upload(landmark.id, "any.png", PNG_BYTES, "image/png")

    assert photo.kind == "upload"
    assert photo.url.startswith("/staging/landmark-albums/%d/" % landmark.id)
    assert photo.license == "用户自传，自行确认版权"
    staged = editor.list_staged(landmark.id)
    assert [item.file for item in staged] == [photo.file]
    assert (project_root / "uploads" / "landmark_albums" / str(landmark.id) / photo.file).read_bytes() == PNG_BYTES


def test_save_upload_rejects_bad_type_and_oversize(editor, landmark):
    with pytest.raises(AlbumEditorError, match="JPG"):
        editor.save_upload(landmark.id, "a.gif", b"x", "image/gif")
    with pytest.raises(AlbumEditorError, match="8MB"):
        editor.save_upload(landmark.id, "a.png", b"x" * (8 * 1024 * 1024 + 1), "image/png")


def test_delete_staged_removes_file_and_rejects_traversal(editor, landmark):
    photo = editor.save_upload(landmark.id, "a.png", PNG_BYTES, "image/png")
    editor.delete_staged(landmark.id, photo.file)
    assert editor.list_staged(landmark.id) == ()

    with pytest.raises(StagingNotFoundError):
        editor.delete_staged(landmark.id, photo.file)
    with pytest.raises(AlbumEditorError, match="非法"):
        editor.delete_staged(landmark.id, "../escape.png")


JPEG_BYTES = b"\xff\xd8\xff\xe0fake-jpeg-content"


def build_full_editor(db_session, project_root, candidates, downloads):
    llm = FakeLLM(
        [
            {"queries": ["应县木塔 实景", "Yingxian Wooden Pagoda"]},
            {"selected": [item.image_url for item in candidates[:2]]},
        ]
    )
    provider = FakeProvider(candidates)
    downloader = downloads.get
    return LandmarkAlbumEditorService(
        db_session, project_root, settings=get_settings(), llm=llm, image_provider=provider, downloader=downloader
    )


def make_candidate(url, title, page=None):
    return type("C", (), {"image_url": url, "title": title, "source_page_url": page, "width": None, "height": None})()


def test_ai_download_saves_candidates_and_records_failures(db_session, project_root, landmark):
    url_a = "https://img.example/a.jpg"
    url_b = "https://img.example/b.png"
    url_bad = "https://img.example/c.svg"
    editor = build_full_editor(
        db_session,
        project_root,
        [make_candidate(url_a, "应县木塔照片", "https://page.example/a"), make_candidate(url_b, "木塔"), make_candidate(url_bad, "坏图")],
        {url_a: (JPEG_BYTES, "image/jpeg"), url_b: (PNG_BYTES, "image/png"), url_bad: (b"<svg>", "image/svg+xml")},
    )

    outcome = editor.ai_download(landmark.id)

    assert [item.file[:3] for item in outcome.saved] == ["ai-", "ai-"]
    assert outcome.saved[0].source_url == "https://page.example/a"
    assert outcome.saved[1].source_url == url_b
    assert outcome.saved[0].license == "网络检索图片，版权待确认"
    assert outcome.saved[0].alt == "应县木塔实景"
    assert len(outcome.failures) == 1
    assert "仅支持" in outcome.failures[0]["reason"]
    assert len(editor.list_staged(landmark.id)) == 2
    # LLM 提示词应包含地标与候选 URL（护栏：只能从候选里选）
    assert "应县木塔" in editor._llm.prompts[0]
    assert url_a in editor._llm.prompts[1]


def test_default_providers_use_commons_without_bocha_key(db_session, project_root):
    """博查无独立图片端点，默认链路应只有 Commons（免 Key）。"""
    editor = LandmarkAlbumEditorService(db_session, project_root, settings=get_settings())
    assert [item.name for item in editor._resolve_providers()] == ["wikimedia_commons"]


def test_commons_provider_parses_license_and_artist():
    import httpx

    from app.integrations.images.wikimedia_commons import WikimediaCommonsImageProvider

    payload = {"query": {"pages": {
        "1": {"title": "File:Yingxian Pagoda.jpg", "imageinfo": [{
            "mime": "image/jpeg", "thumburl": "https://upload.wikimedia.org/t.jpg",
            "url": "https://upload.wikimedia.org/full.jpg", "width": 3000, "height": 4000,
            "thumbwidth": 1600, "thumbheight": 2133,
            "descriptionurl": "https://commons.wikimedia.org/wiki/File:Yingxian_Pagoda.jpg",
            "extmetadata": {"LicenseShortName": {"value": "CC BY-SA 4.0"}, "Artist": {"value": "<a href='#'>张三</a>"}},
        }]},
        "2": {"title": "File:Drawing.svg", "imageinfo": [{"mime": "image/svg+xml", "url": "https://upload.wikimedia.org/d.svg"}]},
    }}}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    provider = WikimediaCommonsImageProvider(transport=httpx.MockTransport(handler))
    result = provider.search("应县木塔")

    assert len(result.candidates) == 1
    candidate = result.candidates[0]
    assert candidate.image_url.endswith("t.jpg")
    assert candidate.license == "CC BY-SA 4.0"
    assert candidate.artist == "张三"
    assert candidate.source_page_url.startswith("https://commons.wikimedia.org/wiki/")


def test_ai_download_carries_commons_license_metadata(db_session, project_root, landmark):
    from app.services.landmark_album_editor import LandmarkAlbumEditorService

    class FakeCommons:
        name = "wikimedia_commons"

        def search(self, query, count=6):
            candidate = type(
                "C", (),
                {"image_url": "https://upload.wikimedia.org/t.jpg", "title": "Yingxian Pagoda",
                 "source_page_url": "https://commons.wikimedia.org/wiki/File:Yingxian_Pagoda.jpg",
                 "width": None, "height": None, "license": "CC BY-SA 4.0", "artist": "张三"},
            )()
            return type("R", (), {"request_id": None, "candidates": (candidate,)})()

    llm = FakeLLM([{"queries": ["应县木塔"]}, {"selected": ["https://upload.wikimedia.org/t.jpg"]}])
    editor = LandmarkAlbumEditorService(
        db_session, project_root, settings=get_settings(), llm=llm,
        image_provider=FakeCommons(),
        downloader={"https://upload.wikimedia.org/t.jpg": (JPEG_BYTES, "image/jpeg")}.get,
    )

    outcome = editor.ai_download(landmark.id)

    assert len(outcome.saved) == 1
    photo = outcome.saved[0]
    assert photo.license == "CC BY-SA 4.0"
    assert photo.credit == "张三"
    assert photo.source_url == "https://commons.wikimedia.org/wiki/File:Yingxian_Pagoda.jpg"


def test_submit_moves_staged_files_and_updates_manifest(db_session, project_root, landmark):
    editor = build_full_editor(
        db_session,
        project_root,
        [make_candidate("https://img.example/ai.jpg", "AI 图")],
        {"https://img.example/ai.jpg": (JPEG_BYTES, "image/jpeg")},
    )
    upload = editor.save_upload(landmark.id, "new.png", PNG_BYTES, "image/png")
    ai = editor.ai_download(landmark.id).saved[0]

    result = editor.submit(
        landmark.id,
        [
            {"kind": "published", "file": "game/existing-landmark/commons-01.jpg", "alt": "旧图保留", "license": "CC BY 4.0"},
            {"kind": "upload", "file": upload.file, "alt": "新上传实景", "license": "自有版权"},
            {"kind": "ai", "file": ai.file, "alt": "AI 下载图", "source_url": "https://page.example/ai"},
        ],
    )

    assert result["added_count"] == 2
    assert result["removed_count"] == 0
    manifest = json.loads((project_root / "data" / "contributions" / "landmark_albums" / "manifest.json").read_text(encoding="utf-8"))
    entries = manifest["albums"]["game:应县木塔"]
    assert len(entries) == 3
    assert entries[0]["file"] == "game/existing-landmark/commons-01.jpg"
    new_files = [entries[1]["file"], entries[2]["file"]]
    assert all(item.startswith("game/existing-landmark/") for item in new_files)
    images_root = project_root / "data" / "contributions" / "landmark_albums" / "images"
    assert all((images_root / item).is_file() for item in new_files)
    # 暂存区已清空，其他地标条目不受影响
    assert editor.list_staged(landmark.id) == ()
    assert "literature:别的地标" in manifest["albums"]


def test_submit_moves_removed_published_to_trash(db_session, project_root, landmark):
    upload = editor_for_trash = None
    editor = LandmarkAlbumEditorService(db_session, project_root, settings=get_settings())
    upload = editor.save_upload(landmark.id, "only.png", PNG_BYTES, "image/png")
    editor.delete_staged(landmark.id, upload.file)
    upload = editor.save_upload(landmark.id, "only.png", PNG_BYTES, "image/png")

    result = editor.submit(
        landmark.id,
        [{"kind": "upload", "file": upload.file, "alt": "替代旧图", "license": "自有版权"}],
    )

    assert result["removed_count"] == 1
    manifest = json.loads((project_root / "data" / "contributions" / "landmark_albums" / "manifest.json").read_text(encoding="utf-8"))
    entries = manifest["albums"]["game:应县木塔"]
    assert len(entries) == 1 and entries[0]["alt"] == "替代旧图"
    trash = list((project_root / "data" / "contributions" / "landmark_albums" / "_trash").iterdir())
    assert len(trash) == 1
    assert not (project_root / "data" / "contributions" / "landmark_albums" / "images" / "game" / "existing-landmark" / "commons-01.jpg").exists()


def test_submit_rejects_missing_alt_and_unknown_published(db_session, project_root, landmark):
    editor = LandmarkAlbumEditorService(db_session, project_root, settings=get_settings())
    upload = editor.save_upload(landmark.id, "a.png", PNG_BYTES, "image/png")

    with pytest.raises(AlbumEditorError, match="缺少图片说明"):
        editor.submit(landmark.id, [{"kind": "upload", "file": upload.file, "alt": "  "}])
    with pytest.raises(AlbumEditorError, match="不存在"):
        editor.submit(landmark.id, [{"kind": "published", "file": "game/nope/x.jpg", "alt": "x"}])


def test_editor_snapshot_lists_published_and_staged(db_session, project_root, landmark):
    editor = LandmarkAlbumEditorService(db_session, project_root, settings=get_settings())
    upload = editor.save_upload(landmark.id, "a.png", PNG_BYTES, "image/png")

    snapshot = editor.editor_snapshot(landmark.id)

    assert snapshot["album_key"] == "game:应县木塔"
    assert snapshot["landmark"]["name"] == "应县木塔"
    assert snapshot["landmark"]["work_title"] == "黑神话：悟空"
    assert [item["kind"] for item in snapshot["published"]] == ["published"]
    assert [item["file"] for item in snapshot["staged"]] == [upload.file]
