"""
Tests for email adapter ABC and factory.
"""

import pytest

from empla.integrations.base import AdapterResult
from empla.integrations.email.base import EmailAdapter
from empla.integrations.email.factory import create_email_adapter
from empla.integrations.email.gmail import GmailEmailAdapter


def test_create_email_adapter_gmail():
    """Factory returns GmailEmailAdapter for 'gmail' provider."""
    adapter = create_email_adapter("gmail", "test@gmail.com")
    assert isinstance(adapter, GmailEmailAdapter)
    assert adapter._email_address == "test@gmail.com"


def test_create_email_adapter_microsoft_graph_not_implemented():
    """Factory raises NotImplementedError for microsoft_graph."""
    with pytest.raises(NotImplementedError, match="Outlook adapter"):
        create_email_adapter("microsoft_graph", "test@outlook.com")


def test_create_email_adapter_unknown_provider():
    """Factory raises ValueError for unknown providers."""
    with pytest.raises(ValueError, match="Unknown email provider"):
        create_email_adapter("unknown_provider", "test@example.com")


def test_email_adapter_abc_not_instantiable():
    """EmailAdapter ABC cannot be instantiated directly."""
    with pytest.raises(TypeError):
        EmailAdapter()  # type: ignore[abstract]


def test_adapter_result_defaults():
    """AdapterResult has sensible defaults."""
    result = AdapterResult(success=True)
    assert result.success is True
    assert result.data == {}
    assert result.error is None


def test_adapter_result_with_data():
    """AdapterResult can carry data and error."""
    result = AdapterResult(success=False, data={"key": "val"}, error="something failed")
    assert result.success is False
    assert result.data == {"key": "val"}
    assert result.error == "something failed"
