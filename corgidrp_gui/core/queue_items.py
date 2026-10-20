"""Data handed from the Parser/Builder to the Status Console (phase 4 consumes it)."""
from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field

from .recipes import Recipe


@dataclass
class QueueRequest:
    """One or more recipe chains the user asked to run."""
    chains: list[list[Recipe]]
    outputdir: str
    cpgs_xml: str | None = None
    source: str = "parser"
    created: str = field(default_factory=lambda: _dt.datetime.now().isoformat(timespec="seconds"))

    @property
    def n_recipes(self) -> int:
        return sum(len(c) for c in self.chains)
