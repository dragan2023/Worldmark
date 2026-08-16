"""Client for Bocha AI's Web Search API."""

from collections.abc import Mapping

import httpx

from app.integrations.search.base import SearchReference, SearchResult


class SearchConfigurationError(RuntimeError):
    """Raised before a search request when required local configuration is absent."""


class SearchProviderError(RuntimeError):
    """Raised when the upstream provider rejects or cannot complete a request."""


class BochaWebSearchProvider:
    """Retrieve ranked web references from Bocha without involving an LLM."""

    name = "bocha_web_search"
    endpoint = "https://api.bochaai.com/v1/web-search"

    def __init__(self, api_key: str | None, transport: httpx.BaseTransport | None = None) -> None:
        self._api_key = api_key
        self._transport = transport

    def search(self, query: str) -> SearchResult:
        if not self._api_key:
            raise SearchConfigurationError("BOCHA_API_KEY is not configured.")

        payload = {
            "query": query,
            "freshness": "oneYear",
            "summary": True,
            "count": 8,
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        try:
            # The local Windows Schannel stack cannot establish a TLS session to
            # Bocha. httpx uses Python's TLS implementation; avoiding ambient
            # proxy settings also keeps this server-to-server call deterministic.
            with httpx.Client(timeout=20.0, transport=self._transport, trust_env=False) as client:
                response = client.post(self.endpoint, headers=headers, json=payload)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise SearchProviderError("Bocha web search request failed.") from exc

        body = response.json()
        if body.get("code") not in (None, 200):
            raise SearchProviderError(str(body.get("msg") or "Bocha web search returned an error."))
        data = body.get("data") or body
        pages = data.get("webPages") or {}
        return SearchResult(
            request_id=str(body.get("log_id") or "") or None,
            references=tuple(self._parse_reference(item) for item in pages.get("value", [])),
        )

    @staticmethod
    def _parse_reference(item: Mapping[str, object]) -> SearchReference:
        title = str(item.get("name") or item.get("title") or "Untitled source")
        url = str(item.get("url") or item.get("link") or "")
        text_parts = [str(item[key]) for key in ("snippet", "summary") if item.get(key)]
        return SearchReference(title=title, url=url, snippet="\n".join(text_parts) or None)
