from fastapi import APIRouter

from app.web.contributors import load_contributors_file

router = APIRouter(prefix="/api/v1/contributors", tags=["contributors"])


@router.get("")
def list_contributors() -> dict:
    """Return the contributor list exactly as stored in contributors.json."""
    return load_contributors_file()
