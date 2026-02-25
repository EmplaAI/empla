"""
Email adapter factory.
"""

from empla.integrations.email.base import EmailAdapter
from empla.integrations.email.gmail import GmailEmailAdapter


def create_email_adapter(provider: str, email_address: str) -> EmailAdapter:
    """Create an email adapter for the given provider.

    Args:
        provider: Provider identifier ("gmail", "microsoft_graph").
        email_address: Sender email address for the From header.

    Returns:
        EmailAdapter instance.

    Raises:
        NotImplementedError: If the provider exists but isn't implemented yet.
        ValueError: If the provider is unknown.
    """
    if provider == "gmail":
        return GmailEmailAdapter(email_address=email_address)
    if provider == "microsoft_graph":
        raise NotImplementedError("Outlook adapter not yet implemented")
    raise ValueError(f"Unknown email provider: {provider}")
