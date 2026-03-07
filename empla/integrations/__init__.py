"""
Integration Adapter Layer (Layer 2)

Provides provider-specific API adapters between capabilities (Layer 1)
and credential management (Layer 3).

Capabilities delegate to adapters via ABCs. Adapters call provider APIs
and return lightweight AdapterResult dataclasses.

IntegrationRouter provides a FastAPI-style pattern for defining
integration tools in a single file.
"""

from empla.integrations.base import AdapterResult
from empla.integrations.router import IntegrationRouter

__all__ = ["AdapterResult", "IntegrationRouter"]
