from typing import Any

from lunr.query import Query

class Index:
    fields: Any
    def __init__(
        self, inverted_index: bool, fied_vectors: Any, token_set: Any, fields: Any, pipeline: Any, search_pipeline: Any
    ) -> None: ...
    def search(self, query_string: str) -> list[dict[str, Any]]: ...
    def query(self, query: Query, callback: Any = None) -> list[dict[str, Any]]: ...
