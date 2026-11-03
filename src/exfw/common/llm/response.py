from dataclasses import dataclass
from typing import Any


@dataclass
class LLMResponse:
    text: str
    raw: dict[str, Any] | None = None
    error: str | None = None
