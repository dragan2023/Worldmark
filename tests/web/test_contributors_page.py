import json

from app.web.contributors import CONTRIBUTORS_FILE


def _write_contributors(tmp_path, contributors):
    path = tmp_path / "contributors.json"
    path.write_text(json.dumps({"contributors": contributors}, ensure_ascii=False), encoding="utf-8")
    return path


def test_contributors_page_returns_200_and_includes_header_nav(client):
    response = client.get("/contributors")

    assert response.status_code == 200
    assert 'href="/contributors"' in response.text
    assert "共创者" in response.text


def test_contributors_page_shows_empty_state_guide(client, monkeypatch, tmp_path):
    empty_file = tmp_path / "contributors.json"
    empty_file.write_text(json.dumps({"contributors": []}), encoding="utf-8")
    monkeypatch.setattr("app.web.contributors.CONTRIBUTORS_FILE", empty_file)

    response = client.get("/contributors")

    assert response.status_code == 200
    assert "还没有共创者" in response.text
    assert "/contribute" in response.text
    assert "提示词包" in response.text


def test_contributors_page_renders_stored_list(client, monkeypatch, tmp_path):
    contributors = [
        {
            "username": "octocat",
            "github_url": "https://github.com/octocat",
            "first_merged_at": "2026-08-17",
            "merged_entries": 3,
        }
    ]
    contributors_file = _write_contributors(tmp_path, contributors)
    monkeypatch.setattr("app.web.contributors.CONTRIBUTORS_FILE", contributors_file)

    response = client.get("/contributors")

    assert response.status_code == 200
    assert "octocat" in response.text
    assert "https://github.com/octocat" in response.text
    assert "2026-08-17" in response.text
    assert "3" in response.text
    assert "还没有共创者" not in response.text


def test_contributors_page_falls_back_to_empty_on_corrupt_file(client, monkeypatch, tmp_path):
    bad_file = tmp_path / "contributors.json"
    bad_file.write_text("{not-json", encoding="utf-8")
    monkeypatch.setattr("app.web.contributors.CONTRIBUTORS_FILE", bad_file)

    response = client.get("/contributors")

    assert response.status_code == 200
    assert "还没有共创者" in response.text
