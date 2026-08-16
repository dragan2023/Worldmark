import pytest

from app.models.enums import PublicationStatus
from app.services.route_builder import RouteBuilderService, RouteStopDraft, RouteUnavailable
from tests.factories import create_landmark


def test_route_keeps_explicit_stop_order_and_becomes_public(db_session):
    first = create_landmark(db_session, landmark_name="第一站")
    second = create_landmark(db_session, landmark_name="第二站")

    service = RouteBuilderService(db_session)
    route = service.create(
        "山西示例路线",
        "按建议顺序访问。",
        "半日",
        [RouteStopDraft(second.id, 50, "先到这里"), RouteStopDraft(first.id, 30, "再到这里")],
    )
    service.publish(route.id)
    public_route = service.get_public(route.id)

    assert route.status == PublicationStatus.PUBLISHED
    assert [stop.landmark_name for stop in public_route.stops] == ["第二站", "第一站"]
    assert public_route.stops[0].stay_minutes == 50


def test_route_is_unavailable_when_a_published_stop_is_removed(db_session):
    first = create_landmark(db_session, landmark_name="第一站")
    second = create_landmark(db_session, landmark_name="第二站")
    service = RouteBuilderService(db_session)
    route = service.create("示例路线", None, None, [RouteStopDraft(first.id), RouteStopDraft(second.id)])
    service.publish(route.id)
    second.published_at = None
    db_session.commit()

    with pytest.raises(RouteUnavailable, match="no longer published"):
        service.get_public(route.id)
