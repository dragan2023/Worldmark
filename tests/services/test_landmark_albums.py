"""相册读取：新键优先、旧键临时兼容、不安全路径拒绝。"""

import json

from app.services.landmark_albums import LandmarkAlbumService, album_key, legacy_album_key


def _write_manifest(tmp_path, albums: dict) -> None:
    manifest_path = tmp_path / "data" / "contributions" / "landmark_albums" / "manifest.json"
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text(
        json.dumps({"schema_version": 1, "albums": albums}, ensure_ascii=False), encoding="utf-8"
    )


def test_reads_stable_landmark_key_and_rejects_unsafe_paths(tmp_path):
    _write_manifest(
        tmp_path,
        {
            album_key(7): [
                {"file": "literature/test/photo.webp", "alt": "测试地标外观", "credit": "共创者", "license": "CC BY 4.0"},
                {"file": "../private.jpg", "alt": "不应加载"},
                {"file": "literature/test/photo.webp", "alt": "  "},
            ]
        },
    )

    photos = LandmarkAlbumService(tmp_path).get_photos(7)

    assert len(photos) == 1
    assert photos[0].url == "/contributions/landmark-albums/images/literature/test/photo.webp"
    assert photos[0].credit == "共创者"


def test_legacy_key_is_only_a_fallback(tmp_path):
    _write_manifest(
        tmp_path,
        {
            legacy_album_key("literature", "测试地标"): [
                {"file": "literature/test/legacy.jpg", "alt": "旧键图片"}
            ],
            album_key(9): [{"file": "literature/test/new.jpg", "alt": "新键图片"}],
        },
    )
    service = LandmarkAlbumService(tmp_path)

    # 有稳定键时优先用它，旧键不再参与
    assert [photo.alt for photo in service.get_photos(9, ip_type=None, landmark_name="测试地标")] == ["新键图片"]
    # 尚未迁移的历史条目仍可读（临时兼容）
    assert [photo.alt for photo in service.get_photos(10, ip_type="literature", landmark_name="测试地标")] == ["旧键图片"]
    # 不提供旧键上下文时不会误读到别的条目
    assert service.get_photos(10) == ()


def test_missing_manifest_returns_empty(tmp_path):
    assert LandmarkAlbumService(tmp_path).get_photos(1) == ()
    assert LandmarkAlbumService(tmp_path).first_photo_url(1) is None
