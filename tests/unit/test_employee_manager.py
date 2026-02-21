"""
Unit tests for EmployeeManager (subprocess backend).

Tests lifecycle operations by mocking subprocess.Popen and DB sessions.
"""

import signal
import subprocess
from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock, Mock, patch
from uuid import UUID, uuid4

import pytest

from empla.services.employee_manager import (
    EmployeeManager,
    UnsupportedRoleError,
    get_employee_manager,
)

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture(autouse=True)
def reset_singleton() -> Generator[None, None, None]:
    """Reset EmployeeManager singleton between tests."""
    EmployeeManager.reset_singleton()
    yield
    EmployeeManager.reset_singleton()


@pytest.fixture
def manager() -> EmployeeManager:
    """Create a fresh EmployeeManager."""
    return EmployeeManager()


@pytest.fixture
def employee_id() -> UUID:
    return uuid4()


@pytest.fixture
def tenant_id() -> UUID:
    return uuid4()


@pytest.fixture
def mock_session() -> AsyncMock:
    """Create a mock async DB session."""
    return AsyncMock()


def _make_db_employee(eid: UUID, tid: UUID) -> Mock:
    """Create a mock DB employee record."""
    emp = Mock()
    emp.id = eid
    emp.tenant_id = tid
    emp.name = "Test Employee"
    emp.role = "sales_ae"
    emp.email = f"test-{eid}@example.com"
    emp.status = "onboarding"
    emp.capabilities = ["email"]
    emp.deleted_at = None
    emp.activated_at = None
    return emp


@pytest.fixture
def mock_db_employee(employee_id: UUID, tenant_id: UUID) -> Mock:
    """Create a mock DB employee record."""
    return _make_db_employee(employee_id, tenant_id)


def _setup_session_with_employee(session: AsyncMock, db_employee: Mock) -> None:
    """Configure mock session to return the given employee."""
    result = MagicMock()
    result.scalar_one_or_none.return_value = db_employee
    session.execute = AsyncMock(return_value=result)
    session.commit = AsyncMock()


def _mock_popen() -> MagicMock:
    """Create a mock Popen that looks alive."""
    proc = MagicMock()
    proc.pid = 12345
    proc.poll.return_value = None  # Process is alive
    proc.returncode = None
    proc.wait.return_value = 0
    proc.send_signal = MagicMock()
    proc.kill = MagicMock()
    proc.stderr = None
    return proc


# ============================================================================
# Test: Initialization
# ============================================================================


def test_singleton_pattern():
    """Test EmployeeManager is a singleton."""
    m1 = EmployeeManager()
    m2 = EmployeeManager()
    assert m1 is m2


def test_get_employee_manager_returns_singleton():
    """Test get_employee_manager returns singleton."""
    m1 = get_employee_manager()
    m2 = get_employee_manager()
    assert m1 is m2


def test_manager_starts_with_empty_processes(manager: EmployeeManager):
    """Test manager starts with no running processes."""
    assert manager.list_running() == []


# ============================================================================
# Test: Start Employee
# ============================================================================


@pytest.mark.asyncio
@patch("empla.services.employee_manager.subprocess.Popen")
async def test_start_employee_spawns_subprocess(
    mock_popen_cls: MagicMock,
    manager: EmployeeManager,
    employee_id: UUID,
    tenant_id: UUID,
    mock_session: AsyncMock,
    mock_db_employee: Mock,
):
    """Test start_employee spawns a subprocess."""
    _setup_session_with_employee(mock_session, mock_db_employee)
    proc = _mock_popen()
    mock_popen_cls.return_value = proc

    status = await manager.start_employee(employee_id, tenant_id, mock_session)

    assert status["is_running"] is True
    mock_popen_cls.assert_called_once()

    # Verify the command includes empla.runner
    cmd = mock_popen_cls.call_args[0][0]
    assert "-m" in cmd
    assert "empla.runner" in cmd
    assert str(employee_id) in cmd
    assert str(tenant_id) in cmd


@pytest.mark.asyncio
@patch("empla.services.employee_manager.subprocess.Popen")
async def test_start_employee_updates_db_status(
    mock_popen_cls: MagicMock,
    manager: EmployeeManager,
    employee_id: UUID,
    tenant_id: UUID,
    mock_session: AsyncMock,
    mock_db_employee: Mock,
):
    """Test start_employee updates DB status to active."""
    _setup_session_with_employee(mock_session, mock_db_employee)
    mock_popen_cls.return_value = _mock_popen()

    await manager.start_employee(employee_id, tenant_id, mock_session)

    assert mock_db_employee.status == "active"
    assert mock_db_employee.activated_at is not None
    mock_session.commit.assert_called()


@pytest.mark.asyncio
@patch("empla.services.employee_manager.subprocess.Popen")
async def test_start_employee_raises_if_already_running(
    mock_popen_cls: MagicMock,
    manager: EmployeeManager,
    employee_id: UUID,
    tenant_id: UUID,
    mock_session: AsyncMock,
    mock_db_employee: Mock,
):
    """Test start_employee raises RuntimeError if already running."""
    _setup_session_with_employee(mock_session, mock_db_employee)
    mock_popen_cls.return_value = _mock_popen()

    await manager.start_employee(employee_id, tenant_id, mock_session)

    with pytest.raises(RuntimeError, match="already running"):
        await manager.start_employee(employee_id, tenant_id, mock_session)


@pytest.mark.asyncio
async def test_start_employee_raises_if_not_found(
    manager: EmployeeManager, tenant_id: UUID, mock_session: AsyncMock
):
    """Test start_employee raises ValueError if employee not found."""
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    mock_session.execute = AsyncMock(return_value=result)

    with pytest.raises(ValueError, match="not found"):
        await manager.start_employee(uuid4(), tenant_id, mock_session)


@pytest.mark.asyncio
async def test_start_employee_raises_for_unsupported_role(
    manager: EmployeeManager,
    employee_id: UUID,
    tenant_id: UUID,
    mock_session: AsyncMock,
    mock_db_employee: Mock,
):
    """Test start_employee raises UnsupportedRoleError for unknown roles."""
    mock_db_employee.role = "robot_overlord"
    _setup_session_with_employee(mock_session, mock_db_employee)

    with pytest.raises(UnsupportedRoleError):
        await manager.start_employee(employee_id, tenant_id, mock_session)


# ============================================================================
# Test: Stop Employee
# ============================================================================


@pytest.mark.asyncio
@patch("empla.services.employee_manager.subprocess.Popen")
async def test_stop_employee_sends_sigterm(
    mock_popen_cls: MagicMock,
    manager: EmployeeManager,
    employee_id: UUID,
    tenant_id: UUID,
    mock_session: AsyncMock,
    mock_db_employee: Mock,
):
    """Test stop_employee sends SIGTERM to subprocess."""
    _setup_session_with_employee(mock_session, mock_db_employee)
    proc = _mock_popen()
    mock_popen_cls.return_value = proc

    await manager.start_employee(employee_id, tenant_id, mock_session)

    # Make process respond to SIGTERM
    proc.poll.return_value = None  # Still alive at first
    proc.wait.return_value = 0  # Then exits

    await manager.stop_employee(employee_id)

    proc.send_signal.assert_called_once_with(signal.SIGTERM)
    assert employee_id not in manager._processes


@pytest.mark.asyncio
async def test_stop_employee_raises_if_not_running(manager: EmployeeManager):
    """Test stop_employee raises ValueError if employee not running."""
    with pytest.raises(ValueError, match="is not running"):
        await manager.stop_employee(uuid4())


@pytest.mark.asyncio
@patch("empla.services.employee_manager.subprocess.Popen")
async def test_stop_employee_updates_db(
    mock_popen_cls: MagicMock,
    manager: EmployeeManager,
    employee_id: UUID,
    tenant_id: UUID,
    mock_session: AsyncMock,
    mock_db_employee: Mock,
):
    """Test stop_employee updates DB status to stopped."""
    _setup_session_with_employee(mock_session, mock_db_employee)
    proc = _mock_popen()
    mock_popen_cls.return_value = proc

    await manager.start_employee(employee_id, tenant_id, mock_session)

    # Reset mock to track stop calls
    mock_session.execute.reset_mock()
    mock_session.commit.reset_mock()

    await manager.stop_employee(employee_id, mock_session)

    # Should have executed an update and committed
    mock_session.execute.assert_called()
    mock_session.commit.assert_called()


# ============================================================================
# Test: Pause/Resume (DB-only)
# ============================================================================


@pytest.mark.asyncio
@patch("empla.services.employee_manager.subprocess.Popen")
async def test_pause_employee_updates_db(
    mock_popen_cls: MagicMock,
    manager: EmployeeManager,
    employee_id: UUID,
    tenant_id: UUID,
    mock_session: AsyncMock,
    mock_db_employee: Mock,
):
    """Test pause_employee writes status='paused' to DB."""
    _setup_session_with_employee(mock_session, mock_db_employee)
    mock_popen_cls.return_value = _mock_popen()

    await manager.start_employee(employee_id, tenant_id, mock_session)

    # Reset mock
    mock_session.execute.reset_mock()
    mock_session.commit.reset_mock()

    await manager.pause_employee(employee_id, mock_session)

    mock_session.execute.assert_called_once()
    mock_session.commit.assert_called_once()
    # Verify the update statement sets status='paused'
    stmt = mock_session.execute.call_args[0][0]
    compiled = stmt.compile()
    assert compiled.params["status"] == "paused"


@pytest.mark.asyncio
@patch("empla.services.employee_manager.subprocess.Popen")
async def test_resume_employee_updates_db(
    mock_popen_cls: MagicMock,
    manager: EmployeeManager,
    employee_id: UUID,
    tenant_id: UUID,
    mock_session: AsyncMock,
    mock_db_employee: Mock,
):
    """Test resume_employee writes status='active' to DB."""
    _setup_session_with_employee(mock_session, mock_db_employee)
    mock_popen_cls.return_value = _mock_popen()

    await manager.start_employee(employee_id, tenant_id, mock_session)

    # Reset mock
    mock_session.execute.reset_mock()
    mock_session.commit.reset_mock()

    await manager.resume_employee(employee_id, mock_session)

    mock_session.execute.assert_called_once()
    mock_session.commit.assert_called_once()
    # Verify the update statement sets status='active'
    stmt = mock_session.execute.call_args[0][0]
    compiled = stmt.compile()
    assert compiled.params["status"] == "active"


@pytest.mark.asyncio
async def test_pause_raises_if_not_running(manager: EmployeeManager, mock_session: AsyncMock):
    """Test pause_employee raises ValueError if not running."""
    with pytest.raises(ValueError, match="is not running"):
        await manager.pause_employee(uuid4(), mock_session)


@pytest.mark.asyncio
async def test_resume_raises_if_not_running(manager: EmployeeManager, mock_session: AsyncMock):
    """Test resume_employee raises ValueError if not running."""
    with pytest.raises(ValueError, match="is not running"):
        await manager.resume_employee(uuid4(), mock_session)


# ============================================================================
# Test: Status
# ============================================================================


def test_get_status_not_running(manager: EmployeeManager):
    """Test get_status returns not running for unknown employee."""
    status = manager.get_status(uuid4())
    assert status["is_running"] is False


@pytest.mark.asyncio
@patch("empla.services.employee_manager.subprocess.Popen")
async def test_get_status_running(
    mock_popen_cls: MagicMock,
    manager: EmployeeManager,
    employee_id: UUID,
    tenant_id: UUID,
    mock_session: AsyncMock,
    mock_db_employee: Mock,
):
    """Test get_status returns running for active subprocess."""
    _setup_session_with_employee(mock_session, mock_db_employee)
    proc = _mock_popen()
    mock_popen_cls.return_value = proc

    await manager.start_employee(employee_id, tenant_id, mock_session)

    status = manager.get_status(employee_id)
    assert status["is_running"] is True
    assert status["pid"] == proc.pid


@pytest.mark.asyncio
@patch("empla.services.employee_manager.subprocess.Popen")
async def test_get_status_detects_crashed_process(
    mock_popen_cls: MagicMock,
    manager: EmployeeManager,
    employee_id: UUID,
    tenant_id: UUID,
    mock_session: AsyncMock,
    mock_db_employee: Mock,
):
    """Test get_status detects and reports crashed process."""
    _setup_session_with_employee(mock_session, mock_db_employee)
    proc = _mock_popen()
    mock_popen_cls.return_value = proc

    await manager.start_employee(employee_id, tenant_id, mock_session)

    # Simulate process crash
    proc.poll.return_value = 1
    proc.returncode = 1

    status = manager.get_status(employee_id)
    assert status["is_running"] is False
    assert status["has_error"] is True
    assert "exited with code 1" in status["last_error"]


# ============================================================================
# Test: List / Is Running
# ============================================================================


@pytest.mark.asyncio
@patch("empla.services.employee_manager.subprocess.Popen")
async def test_list_running(
    mock_popen_cls: MagicMock,
    manager: EmployeeManager,
    tenant_id: UUID,
    mock_session: AsyncMock,
):
    """Test list_running returns running employee IDs."""
    eid1 = uuid4()
    eid2 = uuid4()

    for eid in [eid1, eid2]:
        db_emp = _make_db_employee(eid, tenant_id)
        _setup_session_with_employee(mock_session, db_emp)
        mock_popen_cls.return_value = _mock_popen()
        await manager.start_employee(eid, tenant_id, mock_session)

    running = manager.list_running()
    assert eid1 in running
    assert eid2 in running


def test_is_running_false_for_unknown(manager: EmployeeManager):
    """Test is_running returns False for unknown employee."""
    assert manager.is_running(uuid4()) is False


# ============================================================================
# Test: Stop All
# ============================================================================


@pytest.mark.asyncio
@patch("empla.services.employee_manager.subprocess.Popen")
async def test_stop_all(
    mock_popen_cls: MagicMock,
    manager: EmployeeManager,
    tenant_id: UUID,
    mock_session: AsyncMock,
):
    """Test stop_all stops all running employees."""
    eid1 = uuid4()
    eid2 = uuid4()

    for eid in [eid1, eid2]:
        db_emp = _make_db_employee(eid, tenant_id)
        _setup_session_with_employee(mock_session, db_emp)
        mock_popen_cls.return_value = _mock_popen()
        await manager.start_employee(eid, tenant_id, mock_session)

    # Reset to track stop DB calls
    mock_session.execute.reset_mock()
    mock_session.commit.reset_mock()

    result = await manager.stop_all(mock_session)

    assert set(result["stopped"]) == {eid1, eid2}
    assert result["failed"] == []
    assert manager.list_running() == []
    # Verify DB updates were executed
    assert mock_session.execute.call_count >= 2
    assert mock_session.commit.call_count >= 2


# ============================================================================
# Test: Health Port Allocation
# ============================================================================


@pytest.mark.asyncio
@patch("empla.services.employee_manager.subprocess.Popen")
async def test_health_port_sequential(
    mock_popen_cls: MagicMock,
    manager: EmployeeManager,
    tenant_id: UUID,
    mock_session: AsyncMock,
):
    """Test health ports are allocated sequentially."""
    eid1 = uuid4()
    eid2 = uuid4()

    for eid in [eid1, eid2]:
        db_emp = _make_db_employee(eid, tenant_id)
        _setup_session_with_employee(mock_session, db_emp)
        mock_popen_cls.return_value = _mock_popen()
        await manager.start_employee(eid, tenant_id, mock_session)

    port1 = manager.get_health_port(eid1)
    port2 = manager.get_health_port(eid2)

    assert port1 is not None
    assert port2 is not None
    assert port2 == port1 + 1


# ============================================================================
# Test: SIGKILL Fallback
# ============================================================================


@pytest.mark.asyncio
@patch("empla.services.employee_manager.subprocess.Popen")
async def test_stop_employee_sends_sigkill_on_timeout(
    mock_popen_cls: MagicMock,
    manager: EmployeeManager,
    employee_id: UUID,
    tenant_id: UUID,
    mock_session: AsyncMock,
    mock_db_employee: Mock,
):
    """Test stop_employee sends SIGKILL when SIGTERM times out."""
    _setup_session_with_employee(mock_session, mock_db_employee)
    proc = _mock_popen()
    mock_popen_cls.return_value = proc

    await manager.start_employee(employee_id, tenant_id, mock_session)

    # Make proc.wait raise TimeoutExpired on first call (SIGTERM wait),
    # then return 0 on second call (SIGKILL wait)
    proc.wait.side_effect = [
        subprocess.TimeoutExpired(cmd="test", timeout=30),
        0,
    ]

    await manager.stop_employee(employee_id)

    proc.send_signal.assert_called_once_with(signal.SIGTERM)
    proc.kill.assert_called_once()
    assert employee_id not in manager._processes


# ============================================================================
# Test: Pause/Resume Guards
# ============================================================================


@pytest.mark.asyncio
@patch("empla.services.employee_manager.subprocess.Popen")
async def test_pause_raises_if_process_exited(
    mock_popen_cls: MagicMock,
    manager: EmployeeManager,
    employee_id: UUID,
    tenant_id: UUID,
    mock_session: AsyncMock,
    mock_db_employee: Mock,
):
    """Test pause raises ValueError when subprocess has crashed."""
    _setup_session_with_employee(mock_session, mock_db_employee)
    proc = _mock_popen()
    mock_popen_cls.return_value = proc

    await manager.start_employee(employee_id, tenant_id, mock_session)

    # Simulate process exit
    proc.poll.return_value = 1

    with pytest.raises(ValueError, match="process has exited"):
        await manager.pause_employee(employee_id, mock_session)


@pytest.mark.asyncio
@patch("empla.services.employee_manager.subprocess.Popen")
async def test_resume_raises_if_process_exited(
    mock_popen_cls: MagicMock,
    manager: EmployeeManager,
    employee_id: UUID,
    tenant_id: UUID,
    mock_session: AsyncMock,
    mock_db_employee: Mock,
):
    """Test resume raises ValueError when subprocess has crashed."""
    _setup_session_with_employee(mock_session, mock_db_employee)
    proc = _mock_popen()
    mock_popen_cls.return_value = proc

    await manager.start_employee(employee_id, tenant_id, mock_session)

    # Simulate process exit
    proc.poll.return_value = 1

    with pytest.raises(ValueError, match="process has exited"):
        await manager.resume_employee(employee_id, mock_session)


# ============================================================================
# Test: Tenant ID Tracking
# ============================================================================


@pytest.mark.asyncio
@patch("empla.services.employee_manager.subprocess.Popen")
async def test_tenant_id_stored_on_start(
    mock_popen_cls: MagicMock,
    manager: EmployeeManager,
    employee_id: UUID,
    tenant_id: UUID,
    mock_session: AsyncMock,
    mock_db_employee: Mock,
):
    """Test tenant_id is tracked when employee starts."""
    _setup_session_with_employee(mock_session, mock_db_employee)
    mock_popen_cls.return_value = _mock_popen()

    await manager.start_employee(employee_id, tenant_id, mock_session)

    assert manager._tenant_ids[employee_id] == tenant_id


@pytest.mark.asyncio
@patch("empla.services.employee_manager.subprocess.Popen")
async def test_tenant_id_cleaned_up_on_stop(
    mock_popen_cls: MagicMock,
    manager: EmployeeManager,
    employee_id: UUID,
    tenant_id: UUID,
    mock_session: AsyncMock,
    mock_db_employee: Mock,
):
    """Test tenant_id is removed when employee stops."""
    _setup_session_with_employee(mock_session, mock_db_employee)
    mock_popen_cls.return_value = _mock_popen()

    await manager.start_employee(employee_id, tenant_id, mock_session)
    await manager.stop_employee(employee_id)

    assert employee_id not in manager._tenant_ids


# ============================================================================
# Test: SIGTERM TOCTOU Race
# ============================================================================


@pytest.mark.asyncio
@patch("empla.services.employee_manager.subprocess.Popen")
async def test_stop_handles_process_lookup_error(
    mock_popen_cls: MagicMock,
    manager: EmployeeManager,
    employee_id: UUID,
    tenant_id: UUID,
    mock_session: AsyncMock,
    mock_db_employee: Mock,
):
    """Test stop_employee handles ProcessLookupError gracefully."""
    _setup_session_with_employee(mock_session, mock_db_employee)
    proc = _mock_popen()
    mock_popen_cls.return_value = proc

    await manager.start_employee(employee_id, tenant_id, mock_session)

    # Process exits between poll() and send_signal()
    proc.send_signal.side_effect = ProcessLookupError("No such process")

    # Should not raise
    await manager.stop_employee(employee_id)
    assert employee_id not in manager._processes


# ============================================================================
# Test: Stale Process Restart
# ============================================================================


@pytest.mark.asyncio
@patch("empla.services.employee_manager.subprocess.Popen")
async def test_start_cleans_stale_process(
    mock_popen_cls: MagicMock,
    manager: EmployeeManager,
    employee_id: UUID,
    tenant_id: UUID,
    mock_session: AsyncMock,
    mock_db_employee: Mock,
):
    """Test start_employee cleans up stale process entry and restarts."""
    _setup_session_with_employee(mock_session, mock_db_employee)
    proc1 = _mock_popen()
    mock_popen_cls.return_value = proc1

    await manager.start_employee(employee_id, tenant_id, mock_session)

    # Simulate process crash
    proc1.poll.return_value = 1

    # Should succeed — cleans stale entry and starts new subprocess
    proc2 = _mock_popen()
    proc2.pid = 99999
    mock_popen_cls.return_value = proc2

    status = await manager.start_employee(employee_id, tenant_id, mock_session)
    assert status["is_running"] is True
    assert status["pid"] == 99999


# ============================================================================
# Test: list_running Dead Process Pruning
# ============================================================================


@pytest.mark.asyncio
@patch("empla.services.employee_manager.subprocess.Popen")
async def test_list_running_prunes_dead_processes(
    mock_popen_cls: MagicMock,
    manager: EmployeeManager,
    employee_id: UUID,
    tenant_id: UUID,
    mock_session: AsyncMock,
    mock_db_employee: Mock,
):
    """Test list_running removes dead processes from tracking."""
    _setup_session_with_employee(mock_session, mock_db_employee)
    proc = _mock_popen()
    mock_popen_cls.return_value = proc

    await manager.start_employee(employee_id, tenant_id, mock_session)
    assert employee_id in manager.list_running()

    # Simulate process death
    proc.poll.return_value = 0
    proc.returncode = 0

    running = manager.list_running()
    assert employee_id not in running


# ============================================================================
# Test: stop_all Partial Failure
# ============================================================================


@pytest.mark.asyncio
@patch("empla.services.employee_manager.subprocess.Popen")
async def test_stop_all_continues_on_failure(
    mock_popen_cls: MagicMock,
    manager: EmployeeManager,
    tenant_id: UUID,
    mock_session: AsyncMock,
):
    """Test stop_all continues stopping others if one fails."""
    eid1 = uuid4()
    eid2 = uuid4()

    for eid in [eid1, eid2]:
        db_emp = _make_db_employee(eid, tenant_id)
        _setup_session_with_employee(mock_session, db_emp)
        mock_popen_cls.return_value = _mock_popen()
        await manager.start_employee(eid, tenant_id, mock_session)

    # Make first employee's stop fail by making send_signal raise
    proc1 = manager._processes[eid1]
    proc1.send_signal.side_effect = Exception("boom")
    proc1.poll.return_value = None
    proc1.wait.side_effect = Exception("boom")

    # No session passed — this test focuses on partial-failure resilience.
    # DB update path is covered by test_stop_all.
    result = await manager.stop_all()

    # One should have succeeded, one failed
    assert len(result["stopped"]) + len(result["failed"]) == 2
    assert eid1 in result["failed"]
    assert eid2 in result["stopped"]
