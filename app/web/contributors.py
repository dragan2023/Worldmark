from pathlib import Path
import json

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONTRIBUTORS_FILE = PROJECT_ROOT / "data" / "contributions" / "contributors.json"

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parents[1] / "templates"))


def load_contributors_file(path: Path | None = None) -> dict:
    """Read the contributor list file on every request (never cached).

    The file is maintained by the publish pipeline; this keeps the page and
    the public API exactly in sync with data/contributions/contributors.json.
    """
    path = path or CONTRIBUTORS_FILE
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("contributors"), list):
            return data
    except (OSError, ValueError):
        pass
    return {"contributors": []}


@router.get("/contributors", response_class=HTMLResponse, include_in_schema=False)
def contributors_page(request: Request) -> HTMLResponse:
    data = load_contributors_file()
    return templates.TemplateResponse(
        request,
        "contributors/index.html",
        {"title": "共创者名单｜IP 地标旅游", "contributors": data.get("contributors", [])},
    )
