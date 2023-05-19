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


def chunker(it: Iterable[T], n: int) -> Generator[Sequence[T], None, None]:
    if n < 1:
        raise ValueError("n must be at least one")
    it = iter(it)
    while True:
        chunk_it = islice(it, n)
        try:
            first_el = next(chunk_it)
        except StopIteration:
            return
        yield tuple(chain((first_el,), chunk_it))
