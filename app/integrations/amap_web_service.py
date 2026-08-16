from dataclasses import dataclass
from typing import Any

import httpx


class AmapConfigurationError(RuntimeError):
    """Raised when the optional Web service key is not configured."""


class AmapServiceError(RuntimeError):
    """Raised when Amap rejects or cannot complete a Web service request."""


@dataclass(frozen=True)
class AmapPoi:
    poi_id: str
    name: str
    address: str
    location: str | None
    reference_cost: int | None = None
    rating: float | None = None


class AmapWebService:
    """Small anti-corruption client for Amap Web Service APIs."""

    # The Basic Search service enabled for this project maps to the v3 POI API.
    # Keep the v5 API out of this client unless its separate service entitlement is
    # explicitly required in a later phase.
    poi_endpoint = "https://restapi.amap.com/v3/place/text"
    geocode_endpoint = "https://restapi.amap.com/v3/geocode/geo"
    walking_endpoint = "https://restapi.amap.com/v5/direction/walking"

    def __init__(self, api_key: str | None, transport: httpx.BaseTransport | None = None) -> None:
        self._api_key = api_key
        self._transport = transport

    def search_poi(
        self, keywords: str, city: str | None = None, page_size: int = 10, *, include_details: bool = False
    ) -> tuple[AmapPoi, ...]:
        normalized_keywords = keywords.strip()
        if not normalized_keywords:
            raise ValueError("POI keywords cannot be empty.")
        payload: dict[str, Any] = {
            "key": self._key(),
            "keywords": normalized_keywords,
            "offset": min(max(page_size, 1), 25),
            "page": 1,
            "extensions": "all" if include_details else "base",
        }
        if city:
            payload["city"] = city.strip()
            payload["citylimit"] = "true"
        body = self._get(self.poi_endpoint, payload)
        pois = body.get("pois") or body.get("data") or []
        return tuple(
            AmapPoi(
                poi_id=str(item.get("id") or item.get("poi_id") or ""),
                name=str(item.get("name") or ""),
                address=str(item.get("address") or ""),
                location=str(item.get("location")) if item.get("location") else None,
                reference_cost=self._positive_int((item.get("biz_ext") or {}).get("cost")),
                rating=self._positive_float((item.get("biz_ext") or {}).get("rating")),
            )
            for item in pois
        )

    @staticmethod
    def _positive_int(value: object) -> int | None:
        try:
            parsed = int(float(str(value)))
        except (TypeError, ValueError):
            return None
        return parsed if parsed > 0 else None

    @staticmethod
    def _positive_float(value: object) -> float | None:
        try:
            parsed = float(str(value))
        except (TypeError, ValueError):
            return None
        return parsed if parsed > 0 else None

    def geocode(self, address: str, city: str | None = None) -> str | None:
        params: dict[str, Any] = {"key": self._key(), "address": address}
        if city:
            params["city"] = city
        body = self._get(self.geocode_endpoint, params)
        geocodes = body.get("geocodes") or []
        return str(geocodes[0].get("location")) if geocodes and geocodes[0].get("location") else None

    def walking_distance(self, origin: str, destination: str) -> dict[str, int] | None:
        body = self._get(
            self.walking_endpoint,
            {"key": self._key(), "origin": origin, "destination": destination, "show_fields": "cost"},
        )
        route = body.get("route") or {}
        paths = route.get("paths") or []
        if not paths:
            return None
        path = paths[0]
        return {"distance_meters": int(path.get("distance") or 0), "duration_seconds": int(path.get("cost", {}).get("duration") or path.get("duration") or 0)}

    def _key(self) -> str:
        if not self._api_key:
            raise AmapConfigurationError("AMAP_WEB_SERVICE_API_KEY is not configured.")
        return self._api_key

    def _get(self, endpoint: str, params: dict[str, Any]) -> dict[str, Any]:
        try:
            with httpx.Client(timeout=15.0, transport=self._transport) as client:
                response = client.get(endpoint, params=params)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise AmapServiceError("Amap Web Service request failed.") from exc
        body = response.json()
        if str(body.get("status", "1")) != "1":
            raise AmapServiceError(str(body.get("info") or body.get("infocode") or "Amap Web Service returned an error."))
        return body
