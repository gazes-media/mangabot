import hashlib
from itertools import chain, islice
from typing import Any, Generator, Iterable, Sequence, TypeVar

T = TypeVar("T")


class BraceMessage:
    def __init__(self, fmt: str, /, *args: Any, **kwargs: Any):
        self.fmt = fmt
        self.args = args
        self.kwargs = kwargs

    def __str__(self):
        return self.fmt.format(*self.args, **self.kwargs)


def chunker(iterable: Iterable[T], nb: int) -> Generator[Sequence[T], None, None]:
    if nb < 1:
        raise ValueError("n must be at least one")
    iterable = iter(iterable)
    while True:
        chunk_it = islice(iterable, nb)
        try:
            first_el = next(chunk_it)
        except StopIteration:
            return
        yield tuple(chain((first_el,), chunk_it))


def hash_id(_id: str) -> str:
    return hashlib.md5(_id.encode(), usedforsecurity=False).hexdigest()
