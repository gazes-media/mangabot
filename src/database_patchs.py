from typing import Callable, Coroutine

patchs: list[tuple[int, Callable[[], Coroutine[None, None, None]]]] = []
