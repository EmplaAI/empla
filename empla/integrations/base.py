"""
Base adapter types for the integration layer.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AdapterResult:
    """Result from an adapter operation.

    Lightweight dataclass (not Pydantic) - adapters don't need validation
    overhead. Layer 1 capabilities convert this to ActionResult with metadata.
    """

    success: bool
    data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
