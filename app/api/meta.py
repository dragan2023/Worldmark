from fastapi import APIRouter

from app.schemas.meta import IPTypeListResponse, IPTypeOption

router = APIRouter(prefix="/api/v1/meta", tags=["metadata"])


@router.get("/ip-types", response_model=IPTypeListResponse)
def list_ip_types() -> IPTypeListResponse:
    return IPTypeListResponse(
        items=[
            IPTypeOption(code="literature", name="文学地标"),
            IPTypeOption(code="game", name="游戏地标"),
            IPTypeOption(code="screen", name="影视地标"),
        ]
    )
