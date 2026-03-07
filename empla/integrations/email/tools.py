"""
empla.integrations.email.tools - Email Integration Tools

Defines email tools using the IntegrationRouter pattern.
One file = complete email integration.

Example:
    >>> from empla.integrations.email.tools import router
    >>> await router.initialize({"provider": "gmail", "email_address": "me@co.com"})
    >>> await router.execute_tool("email.send_email", {"to": ["x@co.com"], ...})
"""

from empla.integrations.email.factory import create_email_adapter
from empla.integrations.router import IntegrationRouter

router = IntegrationRouter("email", adapter_factory=create_email_adapter)


@router.tool()
async def send_email(
    to: list[str],
    subject: str,
    body: str,
    cc: list[str] | None = None,
) -> dict:
    """Send a new email to one or more recipients."""
    result = await router.adapter.send(to, subject, body, cc)
    return {"success": result.success, "message_id": result.data.get("message_id")}


@router.tool()
async def reply_to_email(
    email_id: str,
    body: str,
    cc: list[str] | None = None,
) -> dict:
    """Reply to an existing email thread."""
    result = await router.adapter.reply(email_id, body, cc)
    return {"success": result.success, "message_id": result.data.get("message_id")}


@router.tool()
async def forward_email(
    email_id: str,
    to: list[str],
    body: str | None = None,
) -> dict:
    """Forward an email to other recipients."""
    result = await router.adapter.forward(email_id, to, body)
    return {"success": result.success}


@router.tool()
async def get_unread_emails(max_results: int = 10) -> list[dict]:
    """Get unread emails from inbox."""
    emails = await router.adapter.fetch_emails(unread_only=True, max_results=max_results)
    return [
        {
            "id": e.id,
            "from": e.from_addr,
            "subject": e.subject,
            "body": e.body[:500] if e.body else "",
            "timestamp": str(e.timestamp),
        }
        for e in emails
    ]


@router.tool()
async def mark_read(email_id: str) -> dict:
    """Mark an email as read."""
    result = await router.adapter.mark_read(email_id)
    return {"success": result.success}


@router.tool()
async def archive(email_id: str) -> dict:
    """Archive an email."""
    result = await router.adapter.archive(email_id)
    return {"success": result.success}
