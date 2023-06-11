from enum import Enum
from typing import Any

class QueryPresence(Enum):
    OPTIONAL = 1  # default
    REQUIRED = 2
    PROHIBITED = 3  # documents that contain this term will not be returned

class Query:
    WILDCARD_TRAILING: Any
    def __init__(self, fields: list[Any]) -> None: ...
    def term(self, term: str, **kwargs: Any) -> None: ...
