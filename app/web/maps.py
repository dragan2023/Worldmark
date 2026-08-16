from pathlib import Path
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.core.auth import require_entitlement
from app.core.config import Settings, get_settings
from app.models.enums import IPType
from app.web.catalog import MODULES

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parents[1] / "templates"))


@router.get("/maps/{module}", response_class=HTMLResponse, include_in_schema=False)
def map_page(
    module: str,
    request: Request,
    _: object = Depends(require_entitlement("static_map")),
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    if module not in MODULES:
        raise HTTPException(status_code=404, detail="Catalog module not found.")
    if not settings.map_tile_url:
        raise HTTPException(status_code=503, detail="Map tile service is not configured.")
    ip_type, module_name, _work_label = MODULES[module]
    filters = {"ip_type": ip_type.value}
    filters.update({key: value for key, value in request.query_params.items() if key in {"work", "country", "province", "city"} and value})
    return templates.TemplateResponse(
        request,
        "catalog/map.html",
        {
            "request": request,
            "title": f"{module_name}地图｜IP 地标旅游",
            "module_name": module_name,
            "catalog_url": f"/{module}?{urlencode({key: value for key, value in filters.items() if key != 'ip_type'})}",
            "map_api_url": f"/api/v1/maps/landmarks?{urlencode(filters)}",
            "map_tile_url": settings.map_tile_url,
        },
    )
