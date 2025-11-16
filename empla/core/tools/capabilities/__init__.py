"""
empla.core.tools.capabilities - Concrete Tool Implementations

Capability plugins that implement the ToolImplementation protocol.

Each capability provides a collection of related tools:
- email: Send, read, reply to emails (Microsoft Graph, Gmail API)
- calendar: Schedule meetings, check availability (Microsoft Graph, Google Calendar)
- research: Web search, document analysis

Future capabilities:
- crm: Salesforce, HubSpot integration
- communication: Slack, Teams integration
- document: Create presentations, documents, PDFs

Example:
    >>> from empla.core.tools.capabilities.email import SendEmailTool
    >>> from empla.core.tools import ToolRegistry
    >>>
    >>> registry = ToolRegistry()
    >>> registry.register_tool(send_email_tool, SendEmailTool())
"""

# Capabilities will be imported here as they are implemented
# from .email import SendEmailTool, ReadEmailTool, ReplyToEmailTool
# from .calendar import ScheduleMeetingTool, CheckAvailabilityTool

__all__ = [
    # Email capability (coming next)
    # "SendEmailTool",
    # "ReadEmailTool",
    # "ReplyToEmailTool",
    # Calendar capability (future)
    # "ScheduleMeetingTool",
    # "CheckAvailabilityTool",
]
