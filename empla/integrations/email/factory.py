"""
Email adapter factory.
"""

from typing import Any

from empla.integrations.email.base import EmailAdapter
from empla.integrations.email.gmail import GmailEmailAdapter
from empla.integrations.email.types import EmailProvider


class UnknownEmailProviderError(Exception):
    """Raised when an unrecognized email provider is requested."""


def create_email_adapter(provider: str, email_address: str, **kwargs: Any) -> EmailAdapter:
    """Create an email adapter for the given provider.

    Args:
        provider: Provider identifier (e.g. "gmail", "microsoft_graph", "test").
        email_address: Sender email address for the From header.
        **kwargs: Additional provider-specific kwargs (e.g. base_url for test).

    Returns:
        EmailAdapter instance.

    Raises:
        ValueError: If email_address is empty.
        NotImplementedError: If the provider exists but isn't implemented yet.
        UnknownEmailProviderError: If the provider is unknown.
    """
    if not email_address or not email_address.strip():
        raise ValueError("email_address must be a non-empty string")

    if provider == "test":
        from empla.integrations.email.test_adapter import TestEmailAdapter

        return TestEmailAdapter(
            email_address=email_address,
            base_url=kwargs.get("base_url", "http://localhost:9100"),
        )
    if provider == EmailProvider.GMAIL:
        return GmailEmailAdapter(email_address=email_address)
    if provider == EmailProvider.MICROSOFT_GRAPH:
        raise NotImplementedError("Outlook adapter not yet implemented")
    raise UnknownEmailProviderError(f"Unknown email provider: {provider}")
