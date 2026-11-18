"""Enhancement model registry.

A model is a function ``image_bgr -> image_bgr`` plus some metadata that the CLI
and the web UI use to describe it and build its controls. To add a model, create
a module (or package) in ``nautilus/models/`` and decorate a function with
``@register`` -- it is discovered automatically. See ``models/classical.py``.
"""

import importlib
import pkgutil
from dataclasses import dataclass, field
from typing import Any, Callable


class ModelUnavailable(RuntimeError):
    """Raised by a model that cannot run on this machine, e.g. missing weights."""


@dataclass
class Param:
    """A user-tunable parameter, rendered as a control in the web UI.

    type: "float" / "int" (slider), "bool" (checkbox) or "choice" (dropdown).
    """

    name: str
    label: str
    default: Any
    type: str = "float"
    min: float | None = None
    max: float | None = None
    step: float | None = None
    choices: list[str] | None = None
    help: str = ""

    def coerce(self, value):
        if self.type == "bool":
            return value if isinstance(value, bool) else str(value).lower() in ("1", "true", "on", "yes")
        if self.type == "choice":
            if value not in self.choices:
                raise ValueError(f"{self.label}: '{value}' is not one of {self.choices}")
            return value
        value = int(value) if self.type == "int" else float(value)
        if self.min is not None:
            value = max(self.min, value)
        if self.max is not None:
            value = min(self.max, value)
        return value

    def to_json(self):
        return {k: v for k, v in self.__dict__.items() if v is not None}


@dataclass
class Model:
    id: str
    name: str
    description: str
    fn: Callable
    params: list[Param] = field(default_factory=list)
    kind: str = "classical"  # "deep" (neural network) or "classical"
    order: int = 100
    technical: str = ""  # method name and reference, for people who want to look it up
    # Returns None when the model can run, otherwise a message explaining why not.
    check: Callable[[], str | None] = lambda: None
    # Loads weights ahead of the first request (optional).
    preload: Callable[[], None] = lambda: None

    def coerce(self, values: dict | None = None) -> dict:
        values = values or {}
        return {p.name: p.coerce(values.get(p.name, p.default)) for p in self.params}

    def run(self, image_bgr, values: dict | None = None):
        problem = self.check()
        if problem:
            raise ModelUnavailable(problem)
        return self.fn(image_bgr, **self.coerce(values))

    def to_json(self):
        problem = self.check()
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "kind": self.kind,
            "technical": self.technical,
            "available": problem is None,
            "unavailable_reason": problem,
            "params": [p.to_json() for p in self.params],
        }


_REGISTRY: dict[str, Model] = {}


def register(id: str, name: str, description: str = "", params: list[Param] = (),
             kind: str = "classical", order: int = 100, check=None, preload=None, technical: str = ""):
    """Register ``fn(image_bgr, **params) -> image_bgr`` as an enhancement model.

    Models are listed by ``order`` (lowest first); the first one is the default.
    """

    def decorator(fn):
        if id in _REGISTRY:
            raise ValueError(f"Duplicate model id: {id}")
        extra = {k: v for k, v in (("check", check), ("preload", preload)) if v is not None}
        _REGISTRY[id] = Model(id, name, description, fn, list(params), kind, order, technical, **extra)
        return fn

    return decorator


def load_models() -> dict[str, Model]:
    """Import every module in ``nautilus.models`` so their ``@register`` decorators run."""
    from . import models

    for module in pkgutil.iter_modules(models.__path__):
        if not module.name.startswith("_"):
            importlib.import_module(f"{models.__name__}.{module.name}")
    return dict(sorted(_REGISTRY.items(), key=lambda kv: kv[1].order))
