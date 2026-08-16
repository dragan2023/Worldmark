from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class SearchReference:
    title: str
    url: str
    snippet: str | None = None


@dataclass(frozen=True)
class SearchResult:
    request_id: str | None
    references: tuple[SearchReference, ...]


class SearchProvider(Protocol):
    name: str

    def search(self, query: str) -> SearchResult:
        """Return provider references for a single candidate-discovery query."""
