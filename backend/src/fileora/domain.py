from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class FileoraError(Exception):
    def __init__(self, code: str, message: str, status: int = 400):
        self.code, self.message, self.status = code, message, status
        super().__init__(message)


@dataclass
class Unit:
    text: str
    kind: str = "text"
    locator: dict[str, Any] = field(default_factory=dict)
    symbol: str = ""
    asset: str | None = None


@dataclass
class Extraction:
    units: list[Unit]
    warnings: list[str] = field(default_factory=list)
    modality: str = "text"
