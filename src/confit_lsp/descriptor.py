from dataclasses import dataclass
from functools import cached_property
from typing import Any, Iterator, Self, Sequence
from attr import Factory
from lsprotocol.types import Position, Range
import rtoml


from confit_lsp.capabilities import FunctionDescription
from confit_lsp.parsers.toml import parse_toml
from confit_lsp.parsers.types import Element, ElementPath
from confit_lsp.registry import REGISTRY


@dataclass
class ConfigurationView:
    data: dict[str, Any]
    """The actual data."""

    elements: list[Element]
    """Key-value ranges for look-up."""

    @cached_property
    def path2element(self) -> dict[ElementPath, Element]:
        return {element.path: element for element in self.elements}

    def position2element(self, position: Position) -> Element | None:
        for element in self.elements:
            if element.key.start <= position < element.value.end:
                return element
        return None

    def get_factory(self, position: Position) -> FunctionDescription | None:
        element = self.position2element(position)

        if element is None:
            return None

        *path, key = element.path

        if key != "factory":
            return None

        root = self.get_object(path)
        factory_name = root.get("factory")

        if factory_name is None:
            return None

        factory = REGISTRY.get(factory_name)

        if factory is None:
            return None

        return FunctionDescription.from_function(factory_name, factory)

    def get_value(self, path: Sequence[str]) -> Any:
        return self.get_object(path[:-1])[path[-1]]

    def get_object(
        self,
        path: Sequence[str],
    ) -> dict[str, Any]:
        """Get the underlying object at a given path by recursively querying keys."""

        d = self.data

        for key in path:
            d = d[key]

        return d

    @classmethod
    def from_source(cls, content: str) -> Self:
        data = rtoml.loads(content)
        elements = list(parse_toml(content))

        return cls(
            data=data,
            elements=elements,
        )
