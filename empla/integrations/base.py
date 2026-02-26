"""
Base adapter types for the integration layer.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AdapterResult:
    """Result from an adapter operation.

    Uses a plain dataclass rather than Pydantic: adapter results are internal
    return values that don't cross API boundaries, so validation overhead is
    unnecessary.  Layer 1 capabilities convert this to ActionResult with
    metadata before returning to callers.

    See PR #40 for the adapter-layer extraction that introduced this type.
    """

    success: bool
    data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
