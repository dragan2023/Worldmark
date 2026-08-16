import json

from app.models.enums import IPType
from app.services.landmark_albums import LandmarkAlbumService


def test_reads_local_photo_metadata_and_rejects_unsafe_paths(tmp_path):
    manifest_path = tmp_path / "data" / "contributions" / "landmark_albums" / "manifest.json"
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text(
        json.dumps(
            {
                "albums": {
                    "literature:测试地标": [
                        {"file": "literature/test/photo.webp", "alt": "测试地标外观", "credit": "共创者", "license": "CC BY 4.0"},
                        {"file": "../private.jpg", "alt": "不应加载"},
                    ]
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    photos = LandmarkAlbumService(tmp_path).get_photos(IPType.LITERATURE, "测试地标")

    assert len(photos) == 1
    assert photos[0].url == "/contributions/landmark-albums/images/literature/test/photo.webp"
    assert photos[0].credit == "共创者"
