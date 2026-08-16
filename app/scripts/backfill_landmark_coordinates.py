"""为数据库中缺失经纬度的地标地点回填 WGS-84 坐标。

运行方式（项目根目录）：
    .\\.venv\\Scripts\\python.exe -m app.scripts.backfill_landmark_coordinates

说明：
- 中国境内（CN/HK/TW/MO）走高德地理编码（GCJ-02 转 WGS-84）；
- 境外走 Nominatim（遵守 1 请求/秒的限速）；
- 编码失败保留空坐标，绝不编造。
"""

from __future__ import annotations

import sys
import time

from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.location import Location
from app.services.geocoding import GeocodingService

_NOMINATIM_DELAY_SECONDS = 1.2

# 少数境外地点的高德/Nominatim 原始地址无法直接解析，改用知名名称在 Nominatim 中解析后固定坐标。
# 坐标均为 WGS-84，来源标注为对应的 Nominatim 查询。
_MANUAL_OVERRIDES = {
    # Nominatim: "Château d'If, Marseille, France"
    "Château d'If；Île d'If；13007 Marseille France": (43.2798560, 5.3252840),
    # Nominatim: "Hotel Metropol, Moscow, Russia"（莫斯科大都会酒店）
    "Teatralny Proyezd 2；Moscow Russia": (55.7584264, 37.6214880),
    # Nominatim: "Highclere Castle"（海克利尔城堡）
    "Highclere Park；Highclere；Newbury RG20 9RN United Kingdom": (51.3266026, -1.3605135),
}


def main() -> int:
    settings = get_settings()
    amap_key = settings.amap_web_service_api_key.get_secret_value() if settings.amap_web_service_api_key else None
    service = GeocodingService(amap_key)

    with SessionLocal() as db:
        locations = db.scalars(
            select(Location).where(Location.latitude.is_(None), Location.longitude.is_(None)).order_by(Location.id)
        ).all()

        if not locations:
            print("没有需要回填坐标的地点。")
            return 0

        filled = 0
        failed: list[tuple[int, str]] = []
        for index, location in enumerate(locations, start=1):
            coordinates = _MANUAL_OVERRIDES.get(location.normalized_address) or service.geocode(
                location.country_code,
                location.normalized_address,
                location.city_name,
            )
            if coordinates is None:
                failed.append((location.id, location.normalized_address))
                print(f"[{index}/{len(locations)}] 失败  {location.country_code} {location.normalized_address}")
            else:
                latitude, longitude = coordinates
                location.latitude = round(latitude, 6)
                location.longitude = round(longitude, 6)
                filled += 1
                print(f"[{index}/{len(locations)}] 成功  {location.country_code} {location.normalized_address} -> {location.latitude}, {location.longitude}")
            # Nominatim 限速：境外请求之间留出间隔
            if location.country_code not in {"CN", "HK", "TW", "MO"} and index < len(locations):
                time.sleep(_NOMINATIM_DELAY_SECONDS)

        db.commit()

    print(f"\n回填完成：成功 {filled} 条，失败 {len(failed)} 条。")
    if failed:
        for location_id, address in failed:
            print(f"  - 未解析 location_id={location_id}: {address}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
