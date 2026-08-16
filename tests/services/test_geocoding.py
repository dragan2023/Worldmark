import httpx

from app.services.geocoding import GeocodingService, gcj02_to_wgs84, wgs84_to_gcj02


def test_gcj02_roundtrip_is_accurate():
    wgs = (116.404, 39.915)
    gcj = wgs84_to_gcj02(*wgs)
    back = gcj02_to_wgs84(*gcj)
    assert abs(back[0] - wgs[0]) < 1e-6
    assert abs(back[1] - wgs[1]) < 1e-6


def test_out_of_china_coordinates_pass_through():
    # 境外坐标不参与偏转
    assert gcj02_to_wgs84(2.35005, 48.852937) == (2.35005, 48.852937)


def test_china_address_uses_amap_and_converts_to_wgs84():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v3/geocode/geo"
        assert request.url.params["address"] == "北京市东城区安定门外大街地坛公园"
        assert request.url.params["city"] == "北京市"
        # 高德返回 GCJ-02 的 "经度,纬度"
        return httpx.Response(200, json={"status": "1", "geocodes": [{"location": "116.414443,39.953777"}]})

    service = GeocodingService("test-key", amap_transport=httpx.MockTransport(handler))
    latitude, longitude = service.geocode("CN", "北京市东城区安定门外大街地坛公园", "北京市")

    # 已从 GCJ-02 转为 WGS-84，且顺序统一为 (纬度, 经度)
    assert abs(latitude - 39.952372) < 1e-4
    assert abs(longitude - 116.408195) < 1e-4


def test_foreign_address_uses_nominatim_with_normalized_separators():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "nominatim.openstreetmap.org"
        assert request.url.params["q"] == "6 Parvis Notre-Dame, 75004 Paris France"
        return httpx.Response(200, json=[{"lat": "48.8529", "lon": "2.3500"}])

    service = GeocodingService(None, nominatim_transport=httpx.MockTransport(handler))
    assert service.geocode("FR", "6 Parvis Notre-Dame；75004 Paris France") == (48.8529, 2.3500)


def test_nominatim_empty_result_returns_none():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[])

    service = GeocodingService(None, nominatim_transport=httpx.MockTransport(handler))
    assert service.geocode("FR", "no such place") is None


def test_blank_address_returns_none_without_network():
    service = GeocodingService(None)
    assert service.geocode("FR", "   ") is None
