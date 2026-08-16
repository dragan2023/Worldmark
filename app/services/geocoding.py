"""地理编码服务：为地标地点补齐 WGS-84 经纬度。

坐标口径统一为 WGS-84（与 OpenStreetMap 瓦片一致）：
- 中国境内（CN / HK / TW / MO）走高德地理编码，其返回 GCJ-02，需转换为 WGS-84；
- 境外走 Nominatim（OpenStreetMap），返回即为 WGS-84。

约定：任何编码失败（无结果、限流、超时）都返回 None，绝不编造坐标。
"""

from __future__ import annotations

import math

import httpx

from app.integrations.amap_web_service import AmapWebService

# 高德坐标偏转参数（GCJ-02）
_A = 6378245.0
_EE = 0.00669342162296594323

# 走高德的境内国家/地区代码
_AMAP_COUNTRY_CODES = frozenset({"CN", "HK", "TW", "MO"})

_NOMINATIM_ENDPOINT = "https://nominatim.openstreetmap.org/search"
_NOMINATIM_HEADERS = {"User-Agent": "IP-Landmark-Travel/1.0 (landmark coordinate backfill)"}


def _out_of_china(longitude: float, latitude: float) -> bool:
    return not (73.66 <= longitude <= 135.05 and 3.86 <= latitude <= 53.55)


def _transform_latitude(x: float, y: float) -> float:
    value = -100.0 + 2.0 * x + 3.0 * y + 0.2 * y * y + 0.1 * x * y + 0.2 * math.sqrt(abs(x))
    value += (20.0 * math.sin(6.0 * x * math.pi) + 20.0 * math.sin(2.0 * x * math.pi)) * 2.0 / 3.0
    value += (20.0 * math.sin(y * math.pi) + 40.0 * math.sin(y / 3.0 * math.pi)) * 2.0 / 3.0
    value += (160.0 * math.sin(y / 12.0 * math.pi) + 320.0 * math.sin(y * math.pi / 30.0)) * 2.0 / 3.0
    return value


def _transform_longitude(x: float, y: float) -> float:
    value = 300.0 + x + 2.0 * y + 0.1 * x * x + 0.1 * x * y + 0.1 * math.sqrt(abs(x))
    value += (20.0 * math.sin(6.0 * x * math.pi) + 20.0 * math.sin(2.0 * x * math.pi)) * 2.0 / 3.0
    value += (20.0 * math.sin(x * math.pi) + 40.0 * math.sin(x / 3.0 * math.pi)) * 2.0 / 3.0
    value += (150.0 * math.sin(x / 12.0 * math.pi) + 300.0 * math.sin(x / 30.0 * math.pi)) * 2.0 / 3.0
    return value


def wgs84_to_gcj02(longitude: float, latitude: float) -> tuple[float, float]:
    if _out_of_china(longitude, latitude):
        return longitude, latitude
    delta_latitude = _transform_latitude(longitude - 105.0, latitude - 35.0)
    delta_longitude = _transform_longitude(longitude - 105.0, latitude - 35.0)
    rad_latitude = latitude / 180.0 * math.pi
    magic = math.sin(rad_latitude)
    magic = 1 - _EE * magic * magic
    sqrt_magic = math.sqrt(magic)
    delta_latitude = (delta_latitude * 180.0) / ((_A * (1 - _EE)) / (magic * sqrt_magic) * math.pi)
    delta_longitude = (delta_longitude * 180.0) / (_A / sqrt_magic * math.cos(rad_latitude) * math.pi)
    return longitude + delta_longitude, latitude + delta_latitude


def gcj02_to_wgs84(longitude: float, latitude: float) -> tuple[float, float]:
    if _out_of_china(longitude, latitude):
        return longitude, latitude
    wgs_longitude, wgs_latitude = longitude, latitude
    for _ in range(3):
        gcj_longitude, gcj_latitude = wgs84_to_gcj02(wgs_longitude, wgs_latitude)
        wgs_longitude += longitude - gcj_longitude
        wgs_latitude += latitude - gcj_latitude
    return wgs_longitude, wgs_latitude


class GeocodingService:
    """按国家/地区把地址解析为 (latitude, longitude)，统一 WGS-84。"""

    def __init__(
        self,
        amap_key: str | None,
        *,
        amap_transport: httpx.BaseTransport | None = None,
        nominatim_transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._amap = AmapWebService(amap_key, transport=amap_transport)
        self._nominatim_transport = nominatim_transport

    def geocode(self, country_code: str, address: str, city: str | None = None) -> tuple[float, float] | None:
        """返回统一口径的 (latitude, longitude)，失败返回 None。"""
        normalized = address.strip()
        if not normalized:
            return None
        if country_code in _AMAP_COUNTRY_CODES:
            amap_result = self._geocode_amap(normalized, city)
            if amap_result is not None:
                return amap_result
            return self._geocode_nominatim(normalized)
        return self._geocode_nominatim(normalized)

    def _geocode_amap(self, address: str, city: str | None) -> tuple[float, float] | None:
        location = self._amap.geocode(address, city)
        if not location:
            return None
        try:
            longitude, latitude = (float(part) for part in location.split(","))
        except ValueError:
            return None
        wgs_longitude, wgs_latitude = gcj02_to_wgs84(longitude, latitude)
        return wgs_latitude, wgs_longitude

    def _geocode_nominatim(self, address: str) -> tuple[float, float] | None:
        query = self._normalize_query(address)
        try:
            with httpx.Client(timeout=20.0, transport=self._nominatim_transport, headers=_NOMINATIM_HEADERS) as client:
                response = client.get(_NOMINATIM_ENDPOINT, params={"q": query, "format": "json", "limit": 1})
                response.raise_for_status()
        except httpx.HTTPError:
            return None
        results = response.json()
        if not results:
            return None
        try:
            return float(results[0]["lat"]), float(results[0]["lon"])
        except (KeyError, TypeError, ValueError):
            return None

    @staticmethod
    def _normalize_query(address: str) -> str:
        """把全角/半角分号统一成逗号，便于 Nominatim 解析多段地址。"""
        parts = address.replace("；", ",").replace(";", ",").split(",")
        return ", ".join(part.strip() for part in parts if part.strip())
