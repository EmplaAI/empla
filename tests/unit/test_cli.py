"""
Unit tests for empla.cli - Command-Line Interface.

Tests argument parsing and command routing (not actual execution).
"""

from uuid import uuid4

import pytest

from empla.cli import build_parser


def test_parser_builds_successfully():
    """Test parser can be built without errors."""
    parser = build_parser()
    assert parser is not None


def test_parser_start_command():
    """Test parsing start command."""
    eid = str(uuid4())
    tid = str(uuid4())
    parser = build_parser()
    args = parser.parse_args(["employee", "start", eid, "--tenant-id", tid])
    assert args.command == "employee"
    assert args.action == "start"
    assert str(args.employee_id) == eid
    assert str(args.tenant_id) == tid


def test_parser_stop_command():
    """Test parsing stop command."""
    eid = str(uuid4())
    parser = build_parser()
    args = parser.parse_args(["employee", "stop", eid])
    assert args.command == "employee"
    assert args.action == "stop"
    assert str(args.employee_id) == eid


def test_parser_status_command():
    """Test parsing status command."""
    eid = str(uuid4())
    parser = build_parser()
    args = parser.parse_args(["employee", "status", eid])
    assert args.command == "employee"
    assert args.action == "status"


def test_parser_list_command():
    """Test parsing list command."""
    parser = build_parser()
    args = parser.parse_args(["employee", "list"])
    assert args.command == "employee"
    assert args.action == "list"


def test_parser_invalid_uuid_raises():
    """Test parser rejects invalid UUIDs."""
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["employee", "start", "not-a-uuid", "--tenant-id", str(uuid4())])


def test_parser_start_requires_tenant_id():
    """Test start command requires --tenant-id."""
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["employee", "start", str(uuid4())])


def test_cli_module_importable():
    """Test CLI modules can be imported."""
    import empla.cli
    import empla.cli.__main__

    assert empla.cli is not None
