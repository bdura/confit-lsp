from typing import Callable, Iterator, overload

from importlib.metadata import entry_points


from pydantic import HttpUrl


class Registry:
    def __init__(self) -> None:
        self.factories = dict[str, Callable]()

    def get(self, name: str) -> Callable | None:
        return self.factories.get(name)

    @overload
    def register[F: Callable](self, name: str) -> Callable[[F], F]: ...
    @overload
    def register[F: Callable](
        self,
        name: str,
        func: F,
    ) -> F: ...

    def register[F: Callable](
        self,
        name: str,
        func: F | None = None,
    ) -> Callable[[F], F] | F:
        def do_register(f: F) -> F:
            self.factories[name] = f
            return f

        if func is not None:
            return do_register(func)

        return do_register

    def items(self) -> Iterator[tuple[str, Callable]]:
        yield from self.factories.items()


REGISTRY = dict[str, Callable]()


@overload
def register[F: Callable](name: str) -> Callable[[F], F]: ...


@overload
def register[F: Callable](
    name: str,
    func: F,
) -> F: ...


def register[F: Callable](
    name: str,
    func: F | None = None,
) -> Callable[[F], F] | F:
    def do_register(f: F) -> F:
        REGISTRY[name] = f
        return f

    if func is not None:
        return do_register(func)

    return do_register


@register("add")
def add(
    a: float,
    other: float,
) -> float:
    """Add two numbers together."""
    return a + other


@register("multiply")
def multiply(
    a: float,
    b: float = 1.0,
) -> float:
    """Multiply two numbers together."""
    return a * b


@register("something-interesting")
def something(
    a: float,
    b: HttpUrl,
) -> float:
    """Something random."""
    ...


def load_plugins() -> None:
    for plugin in entry_points(group="confit"):
        plugin.load()


load_plugins()
