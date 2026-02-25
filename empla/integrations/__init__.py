"""
Integration Adapter Layer (Layer 2)

Provides provider-specific API adapters between capabilities (Layer 1)
and credential management (Layer 3).

Capabilities delegate to adapters via ABCs. Adapters call provider APIs
and return lightweight AdapterResult dataclasses.
"""

from empla.integrations.base import AdapterResult

__all__ = ["AdapterResult"]
