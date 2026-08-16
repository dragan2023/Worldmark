import httpx
import pytest

from app.integrations.amap_web_service import AmapWebService
from app.services.mock_itinerary_generator import PlannedStop
from app.services.route_optimizer import RouteOptimizer, haversine_meters


def _stop(landmark_id: int, minutes: int = 60) -> PlannedStop:
    return PlannedStop(landmark_id=landmark_id, time_slot="09:00", planned_minutes=minutes, selection_reason="r")


def test_haversine_orders_stops_by_nearest_neighbour():
    coords = {1: (39.0, 113.0), 2: (39.01, 113.01), 3: (40.0, 116.0)}
    optimized = RouteOptimizer(None).optimize_day((_stop(1), _stop(3), _stop(2)), coords)
    assert [stop.landmark_id for stop in optimized] == [1, 2, 3]


def test_keeps_first_stop_fixed():
    coords = {1: (39.0, 113.0), 2: (39.01, 113.01), 3: (40.0, 116.0)}
    optimized = RouteOptimizer(None).optimize_day((_stop(1), _stop(2), _stop(3)), coords)
    assert optimized[0].landmark_id == 1


def test_uses_lodging_anchor_as_the_first_stop_when_available():
    coords = {1: (39.0, 113.0), 2: (39.01, 113.01), 3: (40.0, 116.0)}
    optimized = RouteOptimizer(None).optimize_day((_stop(3), _stop(1), _stop(2)), coords, start_coord=(39.001, 113.001))
    assert [stop.landmark_id for stop in optimized] == [1, 2, 3]


def test_reassigns_time_slots_in_new_order():
    coords = {1: (0.0, 0.0), 2: (0.001, 0.001), 3: (0.002, 0.002)}
    stops = (_stop(1, 60), _stop(2, 90), _stop(3, 30))
    optimized = RouteOptimizer(None).optimize_day(stops, coords)
    assert [stop.time_slot for stop in optimized] == ["09:00", "10:00", "11:30"]


def test_amap_walking_uses_lng_lat_format():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v5/direction/walking"
        seen.append((request.url.params["origin"], request.url.params["destination"]))
        return httpx.Response(200, json={"status": "1", "route": {"paths": [{"distance": "200", "cost": {"duration": "180"}}]}})

    amap = AmapWebService("key", transport=httpx.MockTransport(handler))
    optimizer = RouteOptimizer(amap)
    coords = {1: (39.0, 113.0), 2: (39.01, 113.01), 3: (40.0, 116.0)}
    optimizer.optimize_day((_stop(1), _stop(2), _stop(3)), coords)
    assert ("113.0,39.0", "113.01,39.01") in seen


def test_falls_back_to_haversine_when_amap_fails():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"status": "0"})

    amap = AmapWebService("key", transport=httpx.MockTransport(handler))
    optimizer = RouteOptimizer(amap)
    coords = {1: (39.0, 113.0), 2: (39.01, 113.01), 3: (40.0, 116.0)}
    optimized = optimizer.optimize_day((_stop(1), _stop(3), _stop(2)), coords)
    assert [stop.landmark_id for stop in optimized] == [1, 2, 3]


def test_haversine_meters_sanity():
    beijing = (39.9042, 116.4074)
    shanghai = (31.2304, 121.4737)
    distance = haversine_meters(beijing, shanghai)
    assert 1_000_000 < distance < 1_200_000
