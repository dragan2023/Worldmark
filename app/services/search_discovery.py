from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.integrations.search.base import SearchProvider
from app.integrations.search.bocha_web_search import BochaWebSearchProvider
from app.models.search_run import SearchReferenceRecord, SearchRun


class SearchDiscoveryService:
    def __init__(self, db: Session, settings: Settings | None = None, provider: SearchProvider | None = None) -> None:
        self._db = db
        self._settings = settings or get_settings()
        self._provider = provider or BochaWebSearchProvider(
            api_key=self._settings.bocha_api_key.get_secret_value() if self._settings.bocha_api_key else None,
        )

    def discover(self, query_template: str, query: str) -> SearchRun:
        result = self._provider.search(query)
        search_run = SearchRun(
            provider=self._provider.name,
            query_template=query_template,
            query_text=query,
            requested_at=datetime.now(UTC),
            provider_request_id=result.request_id,
            result_count=len(result.references),
            quota_units=1,
            status="succeeded",
        )
        self._db.add(search_run)
        self._db.flush()
        self._db.add_all(
            SearchReferenceRecord(
                search_run_id=search_run.id,
                position=position,
                title=reference.title,
                url=reference.url,
                snippet=reference.snippet,
            )
            for position, reference in enumerate(result.references, start=1)
            if reference.url
        )
        self._db.commit()
        self._db.refresh(search_run)
        return search_run
