from app.models.enums import IPType
from app.services.landmark_catalog import CatalogFilters, LandmarkCatalogService
from tests.factories import create_landmark


def test_catalog_matches_alias_and_region_and_hides_unpublished(db_session):
    visible = create_landmark(db_session)
    create_landmark(
        db_session,
        work_title="候选游戏",
        aliases="候选别名",
        landmark_name="候选地标",
        published=False,
    )
    create_landmark(
        db_session,
        work_title="影视作品",
        aliases="剧集",
        ip_type=IPType.SCREEN,
        landmark_name="影视地标",
        city_name="江门市",
    )

    result = LandmarkCatalogService(db_session).list(
        CatalogFilters.from_values(IPType.GAME, "Wukong", "cn", "山西省", "朔州市")
    )

    assert result.total == 1
    assert result.items[0].id == visible.id
    assert result.items[0].description_summary.endswith("。")


def test_catalog_pagination_and_public_detail(db_session):
    first = create_landmark(db_session, landmark_name="第一处")
    create_landmark(db_session, landmark_name="第二处")

    service = LandmarkCatalogService(db_session)
    result = service.list(CatalogFilters.from_values(ip_type=IPType.GAME), page=1, page_size=1)
    detail = service.get_detail(first.id)

    assert result.total == 2
    assert len(result.items) == 1
    assert detail.normalized_address
    assert detail.sources[0]["url"].startswith("https://")


def test_get_work_aggregates_its_published_landmarks(db_session):
    first = create_landmark(db_session, work_title="黑神话：悟空", landmark_name="应县木塔")
    create_landmark(db_session, landmark_name="小西天", ip_work=first.ip_work)
    create_landmark(db_session, work_title="别的作品", landmark_name="别的地标")

    work = LandmarkCatalogService(db_session).get_work(first.ip_work_id)

    assert work.title == "黑神话：悟空"
    assert work.total == 2
    assert {entry.name for entry in work.landmarks} == {"应县木塔", "小西天"}
    assert all(entry.work_id == first.ip_work_id for entry in work.landmarks)
