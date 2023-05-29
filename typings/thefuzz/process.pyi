from collections.abc import Iterable
from typing import Callable, TypeVar

T = TypeVar("T")
Q = TypeVar("Q")
P = TypeVar("P")

def extract(
    query: Q,
    choices: Iterable[T],
    processor: Callable[[T | Q], P] = ...,
    scorer: Callable[[P, P], int] = ...,
    limit: int = ...,
) -> list[tuple[T, int]]: ...
