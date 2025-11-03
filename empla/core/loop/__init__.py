"""
empla.core.loop - Proactive Execution Loop

The continuous autonomous operation loop that makes empla employees proactive.

This is the "heartbeat" of empla - it continuously:
1. Perceives environment (gather observations)
2. Updates beliefs (process observations into world model)
3. Reasons strategically (form/abandon goals, generate strategies)
4. Executes intentions (do the highest priority work)
5. Learns from outcomes (update procedural memory, adjust beliefs)

See docs/design/proactive-loop.md for detailed design.
"""

from empla.core.loop.execution import ProactiveExecutionLoop
from empla.core.loop.models import (
    LoopConfig,
    Observation,
    PerceptionResult,
)

__all__ = [
    "LoopConfig",
    "Observation",
    "PerceptionResult",
    "ProactiveExecutionLoop",
]
