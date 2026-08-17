import json

from app.web.contributors import CONTRIBUTORS_FILE


def test_public_contributors_api_returns_stored_file(client, monkeypatch, tmp_path):
    payload = {
        "contributors": [
            {
                "username": "octocat",
                "github_url": "https://github.com/octocat",
                "first_merged_at": "2026-08-17",
                "merged_entries": 2,
            }
        ]
    }
    contributors_file = tmp_path / "contributors.json"
    contributors_file.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr("app.web.contributors.CONTRIBUTORS_FILE", contributors_file)

    response = client.get("/api/v1/contributors")

    assert response.status_code == 200
    assert response.json() == payload


def test_public_contributors_api_empty_list_matches_disk(client):
    response = client.get("/api/v1/contributors")

    assert response.status_code == 200
    assert response.json() == json.loads(CONTRIBUTORS_FILE.read_text(encoding="utf-8"))


def test_public_contributors_api_falls_back_to_empty_on_missing_file(client, monkeypatch, tmp_path):
    missing = tmp_path / "does-not-exist.json"
    monkeypatch.setattr("app.web.contributors.CONTRIBUTORS_FILE", missing)

    response = client.get("/api/v1/contributors")

    assert response.status_code == 200
    assert response.json() == {"contributors": []}
