"""阶段05 回归：发现→详情→行程路径、搜索翻页、共创闭环、地图与可访问性细节。"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.core.auth import create_access_token
from app.models.contribution import LandmarkContribution
from app.models.enums import MembershipTier, PublicationStatus, UserRole, VerificationStatus
from app.models.review import LandmarkReview
from tests.factories import create_admin, create_landmark, create_member


def _headers(user) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


# ------------------------------------------------ 详情页：真实主操作与入口


def test_detail_page_offers_join_itinerary_and_map_actions(client, db_session):
    landmark = create_landmark(db_session, landmark_name="详情动作地标")

    page = client.get(f"/landmarks/{landmark.id}")

    assert page.status_code == 200
    assert f'/itineraries/new?landmark_id={landmark.id}' in page.text
    assert "/maps/games?landmark=" in page.text
    assert "加入行程" in page.text
    # 非编辑者看不到伪可用的编辑入口
    assert "编辑内容与相册" not in page.text


def test_detail_page_shows_edit_entry_only_for_contributor(client, db_session):
    contributor = create_member(db_session, MembershipTier.FREE, role=UserRole.LEVEL1.value)
    landmark = create_landmark(db_session, landmark_name="可编辑地标")
    db_session.add(LandmarkContribution(
        landmark_id=landmark.id, contributor_name=contributor.username, contributor_user_id=contributor.id,
    ))
    db_session.commit()

    page = client.get(f"/landmarks/{landmark.id}", headers=_headers(contributor))

    assert page.status_code == 200
    assert "编辑内容与相册" in page.text


def test_new_itinerary_page_preselects_public_landmark_only(client, db_session):
    import json
    import re

    member = create_member(db_session, MembershipTier.FREE, role=UserRole.LEVEL1.value)
    landmark = create_landmark(db_session, landmark_name="可预选地标")

    page = client.get(f"/itineraries/new?landmark_id={landmark.id}", headers=_headers(member))
    assert page.status_code == 200
    match = re.search(r'id="preselect-landmark">(.*?)</script>', page.text, re.S)
    assert match, "预选数据脚本缺失"
    preselect = json.loads(match.group(1))
    assert preselect["id"] == landmark.id
    assert preselect["name"] == "可预选地标"

    # 未发布/不存在的地标不会被预选，也不会回显名字
    hidden = create_landmark(db_session, landmark_name="未发布地标", published=False)
    hidden_page = client.get(f"/itineraries/new?landmark_id={hidden.id}", headers=_headers(member))
    hidden_match = re.search(r'id="preselect-landmark">(.*?)</script>', hidden_page.text, re.S)
    assert json.loads(hidden_match.group(1)) is None


# ------------------------------------------------------------ 搜索翻页


def test_search_paginates_and_keeps_query(client, db_session):
    for index in range(23):
        create_landmark(db_session, landmark_name=f"搜索分页地标{index:02d}", published=True)

    first = client.get("/search?q=搜索分页地标")
    assert first.status_code == 200
    assert "第 1 / 2 页" in first.text
    assert "q=%E6%90%9C%E7%B4%A2%E5%88%86%E9%A1%B5%E5%9C%B0%E6%A0%87&amp;page=2" in first.text or "page=2" in first.text

    second = client.get("/search?q=搜索分页地标&page=2")
    assert second.status_code == 200
    assert "第 2 / 2 页" in second.text

    beyond = client.get("/search?q=搜索分页地标&page=99")
    assert beyond.status_code == 200
    assert "第 2 / 2 页" in beyond.text  # 超页回到最后一页


def test_search_empty_state_gives_next_steps(client):
    page = client.get("/search?q=不存在的关键词xyz")
    assert page.status_code == 200
    assert "没有匹配的地标" in page.text
    assert "/literature" in page.text and "/intake" in page.text


# ------------------------------------------------------ 我的贡献记录闭环


def _contribution(db_session, *, published: bool, status: VerificationStatus, deleted: bool = False):
    contributor = create_member(db_session, MembershipTier.FREE, role=UserRole.LEVEL2.value)
    landmark = create_landmark(db_session, landmark_name="我的贡献地标", published=False)
    landmark.verification_status = status
    landmark.published_at = datetime.now(UTC) if published else None
    landmark.ip_work.status = PublicationStatus.PUBLISHED if published else PublicationStatus.DRAFT
    if deleted:
        landmark.deleted_at = datetime.now(UTC)
    db_session.add(LandmarkContribution(
        landmark_id=landmark.id, contributor_name=contributor.username, contributor_user_id=contributor.id,
    ))
    db_session.add(LandmarkReview(
        landmark_id=landmark.id, decision=status, reason="来源需要补充", reviewer_name="admin",
    ))
    db_session.commit()
    return contributor, landmark


def test_my_contributions_lists_own_records_with_feedback(client, db_session):
    contributor, landmark = _contribution(db_session, published=False, status=VerificationStatus.CANDIDATE)

    body = client.get("/api/v1/me/contributions", headers=_headers(contributor)).json()

    assert body["total"] == 1
    item = body["items"][0]
    assert item["landmark_id"] == landmark.id
    assert item["status"] == "candidate"
    assert item["review_feedback"]["reason"] == "来源需要补充"
    assert item["can_edit"] is True


def test_my_contributions_never_leaks_other_users_records(client, db_session):
    owner, landmark = _contribution(db_session, published=True, status=VerificationStatus.VERIFIED)
    other = create_member(db_session, MembershipTier.FREE, role=UserRole.LEVEL1.value)

    body = client.get("/api/v1/me/contributions", headers=_headers(other)).json()
    assert body == {"total": 0, "page": 1, "page_size": 10, "total_pages": 1, "items": []}

    page = client.get("/contributions", headers=_headers(other))
    assert page.status_code == 200
    assert "我的贡献地标" not in page.text


def test_deleted_contribution_only_shows_status(client, db_session):
    contributor, landmark = _contribution(
        db_session, published=False, status=VerificationStatus.VERIFIED, deleted=True
    )

    body = client.get("/api/v1/me/contributions", headers=_headers(contributor)).json()
    item = body["items"][0]
    assert item["status"] == "deleted"
    assert item["name"] is None
    assert item["can_edit"] is False


def test_contributions_page_requires_login(client):
    response = client.get("/contributions", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"].startswith("/login?next=")


# ------------------------------------------------------ 地图与可访问性


def test_map_script_stores_group_reference_and_supports_keyboard():
    from pathlib import Path

    script = Path("app/static/js/landmark-map.js").read_text(encoding="utf-8")
    # B06 回归：搜索时整组隐藏必须有真实引用
    assert "group.groupEl = groupEl" in script
    assert "entry.listItem" in script
    page = Path("app/templates/catalog/map.html").read_text(encoding="utf-8")
    assert 'id="map-status"' in page
    assert 'class="visually-hidden"' in page


def test_header_navigation_marks_current_page_and_groups_language(client, db_session):
    create_landmark(db_session)
    page = client.get("/games")

    assert "发现地标" in page.text
    assert "我的行程" in page.text
    assert "参与共创" in page.text
    assert 'aria-current="page"' in page.text


def test_base_template_replaces_duplicated_skeletons():
    from pathlib import Path

    for name in ("home.html", "search.html", "catalog/index.html", "catalog/detail.html",
                 "catalog/map.html", "itineraries/index.html", "itineraries/form.html",
                 "itineraries/detail.html", "contributions/index.html", "error.html"):
        content = Path("app/templates", name).read_text(encoding="utf-8")
        assert content.startswith('{% extends "base.html" %}'), name
        assert "<!doctype html>" not in content, name


def test_album_edit_page_requires_contributor(client, db_session):
    landmark = create_landmark(db_session, landmark_name="相册页权限地标")
    anonymous = client.get(f"/landmarks/{landmark.id}/album/edit", follow_redirects=False)
    assert anonymous.status_code == 303

    stranger = create_member(db_session, MembershipTier.FREE, role=UserRole.LEVEL1.value)
    forbidden = client.get(f"/landmarks/{landmark.id}/album/edit", headers=_headers(stranger))
    assert forbidden.status_code == 403
    assert "贡献者" in forbidden.text


def test_touch_targets_and_contrast_tokens_are_declared():
    from pathlib import Path

    css = Path("app/static/css/site.css").read_text(encoding="utf-8")
    assert "--control-height:44px" in css
    assert "--muted:#6B6150" in css  # 对纸面对比度 5.6:1
    assert "prefers-reduced-motion" in css
