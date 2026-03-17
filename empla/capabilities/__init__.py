"""
empla.capabilities - DEPRECATED

The old capabilities system has been replaced by the tool system
(empla.core.tools). Use ToolRouter, ToolRegistry, and @tool decorator instead.

ActionResult has moved to empla.core.tools.base.
"""

# Capability type constants — kept for role catalog metadata
CAPABILITY_BROWSER = "browser"
CAPABILITY_CALENDAR = "calendar"
CAPABILITY_COMPUTE = "compute"
CAPABILITY_COMPUTER_USE = "computer_use"
CAPABILITY_CRM = "crm"
CAPABILITY_DOCUMENT = "document"
CAPABILITY_EMAIL = "email"
CAPABILITY_MESSAGING = "messaging"
CAPABILITY_VOICE = "voice"
CAPABILITY_WORKSPACE = "workspace"

__all__ = [
    "CAPABILITY_BROWSER",
    "CAPABILITY_CALENDAR",
    "CAPABILITY_COMPUTE",
    "CAPABILITY_COMPUTER_USE",
    "CAPABILITY_CRM",
    "CAPABILITY_DOCUMENT",
    "CAPABILITY_EMAIL",
    "CAPABILITY_MESSAGING",
    "CAPABILITY_VOICE",
    "CAPABILITY_WORKSPACE",
]
