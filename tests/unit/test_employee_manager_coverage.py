"""
Comprehensive tests for empla.services.employee_manager module.

Covers EmployeeManager lifecycle (start, stop, pause, resume),
status checking, health polling, singleton behavior, and error paths.
"""

import asyncio
import signal
import subprocess
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import httpx
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
def reset_singleton():
    """Reset the singleton before each test."""
    EmployeeManager.reset_singleton()
    yield
    EmployeeManager.reset_singleton()


@pytest.fixture
def manager():
    return EmployeeManager()


@pytest.fixture
def employee_id():
    return uuid4()


@pytest.fixture
def tenant_id():
    return uuid4()


def _make_mock_session(db_employee=None):
    """Create a mock async session.

    session.execute is async (awaited). The result object has sync
    methods like scalar_one_or_none().
    """
    session = AsyncMock()
    mock_result = Mock()
    mock_result.scalar_one_or_none.return_value = db_employee
    session.execute.return_value = mock_result
    return session


def _make_db_employee(role: str = "sales_ae", status: str = "stopped"):
    """Create a mock DB employee."""
    emp = Mock()
    emp.id = uuid4()
    emp.role = role
    emp.status = status
    emp.activated_at = None
    emp.deleted_at = None
    return emp


def _make_mock_process(alive: bool = True, pid: int = 12345, returncode: int = 0):
    """Create a mock subprocess.Popen."""
    proc = Mock(spec=subprocess.Popen)
    proc.pid = pid
    proc.returncode = returncode if not alive else None
    proc.poll.return_value = None if alive else returncode
    proc.wait = Mock()
    proc.terminate = Mock()
    proc.kill = Mock()
    proc.send_signal = Mock()
    return proc


# ============================================================================
# Test: Singleton
# ============================================================================


class TestSingleton:
    """Tests for singleton behavior."""

    def test_singleton_returns_same_instance(self):
        """Multiple EmployeeManager() calls return the same instance."""
        m1 = EmployeeManager()
        m2 = EmployeeManager()
        assert m1 is m2

    def test_reset_singleton(self):
        """reset_singleton() creates a new instance on next call."""
        m1 = EmployeeManager()
        EmployeeManager.reset_singleton()
        m2 = EmployeeManager()
        assert m1 is not m2

    def test_get_employee_manager_returns_singleton(self):
        """get_employee_manager() returns the singleton."""
        m1 = get_employee_manager()
        m2 = get_employee_manager()
        assert m1 is m2

    def test_init_only_runs_once(self):
        """__init__ only initializes once (idempotent on singleton)."""
        m = EmployeeManager()
        m._processes["test"] = "value"
        # Re-init should NOT clear _processes
        m.__init__()
        assert "test" in m._processes


# ============================================================================
# Test: start_employee
# ============================================================================


class TestStartEmployee:
    """Tests for start_employee."""

    @pytest.mark.asyncio
    async def test_start_employee_success(self, manager, employee_id, tenant_id):
        """Successfully starts an employee subprocess."""
        db_emp = _make_db_employee(role="sales_ae", status="stopped")
        session = _make_mock_session(db_employee=db_emp)

        mock_proc = _make_mock_process(alive=True, pid=9999)

        with (
            patch(
                "empla.services.employee_manager.get_employee_class",
                return_value=Mock,
            ),
            patch("empla.services.employee_manager.subprocess.Popen", return_value=mock_proc),
        ):
            result = await manager.start_employee(employee_id, tenant_id, session)

            assert result["is_running"] is True
            assert result["id"] == str(employee_id)
            assert result["pid"] == 9999
            assert db_emp.status == "active"
            session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_start_employee_already_running(self, manager, employee_id, tenant_id):
        """Raises RuntimeError if employee is already running."""
        session = AsyncMock()
        manager._processes[employee_id] = _make_mock_process(alive=True)

        with pytest.raises(RuntimeError, match="already running"):
            await manager.start_employee(employee_id, tenant_id, session)

    @pytest.mark.asyncio
    async def test_start_employee_stale_process_cleaned_up(self, manager, employee_id, tenant_id):
        """Cleans up stale (exited) process and starts a new one."""
        db_emp = _make_db_employee(role="sales_ae")
        session = _make_mock_session(db_employee=db_emp)

        # Stale process that has already exited
        stale_proc = _make_mock_process(alive=False, returncode=1)
        manager._processes[employee_id] = stale_proc
        manager._health_ports[employee_id] = 9100
        manager._tenant_ids[employee_id] = tenant_id

        new_proc = _make_mock_process(alive=True, pid=8888)

        with (
            patch("empla.services.employee_manager.get_employee_class", return_value=Mock),
            patch("empla.services.employee_manager.subprocess.Popen", return_value=new_proc),
        ):
            result = await manager.start_employee(employee_id, tenant_id, session)
            assert result["is_running"] is True
            assert result["pid"] == 8888

    @pytest.mark.asyncio
    async def test_start_employee_not_found(self, manager, employee_id, tenant_id):
        """Raises ValueError if employee not found in DB."""
        session = _make_mock_session(db_employee=None)

        with pytest.raises(ValueError, match="not found"):
            await manager.start_employee(employee_id, tenant_id, session)

    @pytest.mark.asyncio
    async def test_start_employee_unsupported_role(self, manager, employee_id, tenant_id):
        """Raises UnsupportedRoleError for unknown roles."""
        db_emp = _make_db_employee(role="unknown_role")
        session = _make_mock_session(db_employee=db_emp)

        with patch("empla.services.employee_manager.get_employee_class", return_value=None):
            with pytest.raises(UnsupportedRoleError, match="Unsupported role"):
                await manager.start_employee(employee_id, tenant_id, session)

    @pytest.mark.asyncio
    async def test_start_employee_db_commit_failure_kills_process(
        self, manager, employee_id, tenant_id
    ):
        """If DB commit fails after spawning, subprocess is killed."""
        db_emp = _make_db_employee(role="sales_ae")
        session = _make_mock_session(db_employee=db_emp)
        session.commit.side_effect = RuntimeError("db down")

        mock_proc = _make_mock_process(alive=True, pid=7777)

        with (
            patch("empla.services.employee_manager.get_employee_class", return_value=Mock),
            patch("empla.services.employee_manager.subprocess.Popen", return_value=mock_proc),
        ):
            with pytest.raises(RuntimeError, match="db down"):
                await manager.start_employee(employee_id, tenant_id, session)

            mock_proc.terminate.assert_called_once()
            assert employee_id not in manager._processes

    @pytest.mark.asyncio
    async def test_start_employee_db_commit_failure_sigkill_on_timeout(
        self, manager, employee_id, tenant_id
    ):
        """If terminate times out, SIGKILL is sent."""
        db_emp = _make_db_employee(role="sales_ae")
        session = _make_mock_session(db_employee=db_emp)
        session.commit.side_effect = RuntimeError("db down")

        mock_proc = _make_mock_process(alive=True)
        # First wait (after terminate) times out, second wait (after kill) succeeds
        mock_proc.wait.side_effect = [subprocess.TimeoutExpired("cmd", 5), None]

        with (
            patch("empla.services.employee_manager.get_employee_class", return_value=Mock),
            patch("empla.services.employee_manager.subprocess.Popen", return_value=mock_proc),
        ):
            with pytest.raises(RuntimeError, match="db down"):
                await manager.start_employee(employee_id, tenant_id, session)

            mock_proc.kill.assert_called_once()

    @pytest.mark.asyncio
    async def test_start_employee_sets_activated_at_if_not_active(
        self, manager, employee_id, tenant_id
    ):
        """activated_at is set when status transitions from non-active."""
        db_emp = _make_db_employee(role="sales_ae", status="stopped")
        session = _make_mock_session(db_employee=db_emp)
        mock_proc = _make_mock_process(alive=True)

        with (
            patch("empla.services.employee_manager.get_employee_class", return_value=Mock),
            patch("empla.services.employee_manager.subprocess.Popen", return_value=mock_proc),
        ):
            await manager.start_employee(employee_id, tenant_id, session)

            assert db_emp.activated_at is not None

    @pytest.mark.asyncio
    async def test_start_employee_already_active_no_activated_at_update(
        self, manager, employee_id, tenant_id
    ):
        """activated_at is NOT changed if already active."""
        db_emp = _make_db_employee(role="sales_ae", status="active")
        session = _make_mock_session(db_employee=db_emp)
        mock_proc = _make_mock_process(alive=True)

        with (
            patch("empla.services.employee_manager.get_employee_class", return_value=Mock),
            patch("empla.services.employee_manager.subprocess.Popen", return_value=mock_proc),
        ):
            await manager.start_employee(employee_id, tenant_id, session)

            # activated_at stays None (not updated since status was already active)
            assert db_emp.activated_at is None

    @pytest.mark.asyncio
    async def test_start_employee_health_port_increments(self, manager, tenant_id):
        """Each start allocates a new health port."""
        ports = []
        for _ in range(3):
            eid = uuid4()
            db_emp = _make_db_employee(role="sales_ae")
            session = _make_mock_session(db_employee=db_emp)
            mock_proc = _make_mock_process(alive=True)

            with (
                patch("empla.services.employee_manager.get_employee_class", return_value=Mock),
                patch("empla.services.employee_manager.subprocess.Popen", return_value=mock_proc),
            ):
                result = await manager.start_employee(eid, tenant_id, session)
                ports.append(result["health_port"])

        assert ports == [9100, 9101, 9102]

    @pytest.mark.asyncio
    async def test_start_employee_clears_error_state(self, manager, employee_id, tenant_id):
        """Starting clears any previous error state."""
        manager._error_states[employee_id] = "Process exited with code 1"

        db_emp = _make_db_employee(role="sales_ae")
        session = _make_mock_session(db_employee=db_emp)
        mock_proc = _make_mock_process(alive=True)

        with (
            patch("empla.services.employee_manager.get_employee_class", return_value=Mock),
            patch("empla.services.employee_manager.subprocess.Popen", return_value=mock_proc),
        ):
            await manager.start_employee(employee_id, tenant_id, session)
            assert employee_id not in manager._error_states


# ============================================================================
# Test: stop_employee
# ============================================================================


class TestStopEmployee:
    """Tests for stop_employee."""

    @pytest.mark.asyncio
    async def test_stop_employee_not_running(self, manager, employee_id):
        """Raises ValueError if employee not running."""
        with pytest.raises(ValueError, match="not running"):
            await manager.stop_employee(employee_id)

    @pytest.mark.asyncio
    async def test_stop_employee_success(self, manager, employee_id, tenant_id):
        """Successfully stops a running employee."""
        mock_proc = _make_mock_process(alive=True, pid=5555)
        manager._processes[employee_id] = mock_proc
        manager._health_ports[employee_id] = 9100
        manager._tenant_ids[employee_id] = tenant_id

        with patch("asyncio.get_running_loop") as loop_mock:
            mock_loop = Mock()
            mock_loop.run_in_executor = AsyncMock()
            loop_mock.return_value = mock_loop

            result = await manager.stop_employee(employee_id)

            mock_proc.send_signal.assert_called_once_with(signal.SIGTERM)
            assert result["is_running"] is False
            assert employee_id not in manager._processes
            assert employee_id not in manager._health_ports
            assert employee_id not in manager._tenant_ids

    @pytest.mark.asyncio
    async def test_stop_employee_already_exited(self, manager, employee_id, tenant_id):
        """Handles process that already exited before stop."""
        mock_proc = _make_mock_process(alive=False, returncode=0)
        manager._processes[employee_id] = mock_proc
        manager._health_ports[employee_id] = 9100
        manager._tenant_ids[employee_id] = tenant_id

        result = await manager.stop_employee(employee_id)
        assert result["is_running"] is False
        # send_signal should not be called since poll() returned non-None
        mock_proc.send_signal.assert_not_called()

    @pytest.mark.asyncio
    async def test_stop_employee_with_db_update(self, manager, employee_id, tenant_id):
        """stop_employee updates DB when session provided."""
        mock_proc = _make_mock_process(alive=False, returncode=0)
        manager._processes[employee_id] = mock_proc
        manager._health_ports[employee_id] = 9100
        manager._tenant_ids[employee_id] = tenant_id

        session = AsyncMock()

        result = await manager.stop_employee(employee_id, session=session)

        session.execute.assert_awaited_once()
        session.commit.assert_awaited_once()
        assert result["is_running"] is False

    @pytest.mark.asyncio
    async def test_stop_employee_sigterm_process_lookup_error(
        self, manager, employee_id, tenant_id
    ):
        """Handles ProcessLookupError when sending SIGTERM."""
        mock_proc = _make_mock_process(alive=True)
        mock_proc.send_signal.side_effect = ProcessLookupError("no such process")
        manager._processes[employee_id] = mock_proc
        manager._tenant_ids[employee_id] = tenant_id

        with patch("asyncio.get_running_loop") as loop_mock:
            mock_loop = Mock()
            mock_loop.run_in_executor = AsyncMock()
            loop_mock.return_value = mock_loop

            result = await manager.stop_employee(employee_id)
            assert result["is_running"] is False

    @pytest.mark.asyncio
    async def test_stop_employee_timeout_then_sigkill(self, manager, employee_id, tenant_id):
        """Sends SIGKILL if SIGTERM times out."""
        mock_proc = _make_mock_process(alive=True, pid=4444)
        manager._processes[employee_id] = mock_proc
        manager._tenant_ids[employee_id] = tenant_id

        with patch("asyncio.get_running_loop") as loop_mock:
            mock_loop = Mock()
            # First call (SIGTERM wait) times out, second call (SIGKILL wait) succeeds
            mock_loop.run_in_executor = AsyncMock(
                side_effect=[subprocess.TimeoutExpired("cmd", 30), None]
            )
            loop_mock.return_value = mock_loop

            result = await manager.stop_employee(employee_id)

            mock_proc.kill.assert_called_once()
            assert result["is_running"] is False

    @pytest.mark.asyncio
    async def test_stop_employee_no_tenant_id_raises_on_db_update(self, manager, employee_id):
        """Raises ValueError if no tenant_id and session is provided."""
        mock_proc = _make_mock_process(alive=False, returncode=0)
        manager._processes[employee_id] = mock_proc
        # Note: no tenant_id set

        session = AsyncMock()
        with pytest.raises(ValueError, match="no tenant_id"):
            await manager.stop_employee(employee_id, session=session)


# ============================================================================
# Test: pause_employee
# ============================================================================


class TestPauseEmployee:
    """Tests for pause_employee."""

    @pytest.mark.asyncio
    async def test_pause_employee_success(self, manager, employee_id, tenant_id):
        """Successfully pauses a running employee."""
        mock_proc = _make_mock_process(alive=True)
        manager._processes[employee_id] = mock_proc
        manager._tenant_ids[employee_id] = tenant_id
        session = AsyncMock()

        result = await manager.pause_employee(employee_id, session)

        session.execute.assert_awaited_once()
        session.commit.assert_awaited_once()
        assert result["is_running"] is True  # Process still alive, just paused in DB

    @pytest.mark.asyncio
    async def test_pause_employee_not_running(self, manager, employee_id):
        """Raises ValueError if employee not running."""
        session = AsyncMock()
        with pytest.raises(ValueError, match="not running"):
            await manager.pause_employee(employee_id, session)

    @pytest.mark.asyncio
    async def test_pause_employee_process_exited(self, manager, employee_id, tenant_id):
        """Raises ValueError if process has exited."""
        mock_proc = _make_mock_process(alive=False)
        manager._processes[employee_id] = mock_proc
        manager._tenant_ids[employee_id] = tenant_id
        session = AsyncMock()

        with pytest.raises(ValueError, match="process has exited"):
            await manager.pause_employee(employee_id, session)

    @pytest.mark.asyncio
    async def test_pause_employee_no_tenant_id(self, manager, employee_id):
        """Raises ValueError if no tenant_id."""
        mock_proc = _make_mock_process(alive=True)
        manager._processes[employee_id] = mock_proc
        # No tenant_id
        session = AsyncMock()

        with pytest.raises(ValueError, match="no tenant_id"):
            await manager.pause_employee(employee_id, session)


# ============================================================================
# Test: resume_employee
# ============================================================================


class TestResumeEmployee:
    """Tests for resume_employee."""

    @pytest.mark.asyncio
    async def test_resume_employee_success(self, manager, employee_id, tenant_id):
        """Successfully resumes a paused employee."""
        mock_proc = _make_mock_process(alive=True)
        manager._processes[employee_id] = mock_proc
        manager._tenant_ids[employee_id] = tenant_id
        session = AsyncMock()

        result = await manager.resume_employee(employee_id, session)

        session.execute.assert_awaited_once()
        session.commit.assert_awaited_once()
        assert result["is_running"] is True

    @pytest.mark.asyncio
    async def test_resume_employee_not_running(self, manager, employee_id):
        """Raises ValueError if employee not running."""
        session = AsyncMock()
        with pytest.raises(ValueError, match="not running"):
            await manager.resume_employee(employee_id, session)

    @pytest.mark.asyncio
    async def test_resume_employee_process_exited(self, manager, employee_id, tenant_id):
        """Raises ValueError if process has exited."""
        mock_proc = _make_mock_process(alive=False)
        manager._processes[employee_id] = mock_proc
        manager._tenant_ids[employee_id] = tenant_id
        session = AsyncMock()

        with pytest.raises(ValueError, match="process has exited"):
            await manager.resume_employee(employee_id, session)

    @pytest.mark.asyncio
    async def test_resume_employee_no_tenant_id(self, manager, employee_id):
        """Raises ValueError if no tenant_id."""
        mock_proc = _make_mock_process(alive=True)
        manager._processes[employee_id] = mock_proc
        session = AsyncMock()

        with pytest.raises(ValueError, match="no tenant_id"):
            await manager.resume_employee(employee_id, session)


# ============================================================================
# Test: get_status
# ============================================================================


class TestGetStatus:
    """Tests for get_status."""

    def test_status_not_tracked(self, manager, employee_id):
        """Returns not-running status for untracked employee."""
        result = manager.get_status(employee_id)
        assert result["is_running"] is False
        assert result["has_error"] is False
        assert result["id"] == str(employee_id)

    def test_status_running(self, manager, employee_id):
        """Returns running status with pid and health_port."""
        mock_proc = _make_mock_process(alive=True, pid=1234)
        manager._processes[employee_id] = mock_proc
        manager._health_ports[employee_id] = 9100

        result = manager.get_status(employee_id)
        assert result["is_running"] is True
        assert result["pid"] == 1234
        assert result["health_port"] == 9100

    def test_status_with_error_state(self, manager, employee_id):
        """Returns error state for employee with recorded error."""
        manager._error_states[employee_id] = "Process exited with code 1"

        result = manager.get_status(employee_id)
        assert result["is_running"] is False
        assert result["has_error"] is True
        assert result["last_error"] == "Process exited with code 1"

    def test_status_prunes_dead_process(self, manager, employee_id):
        """Prunes dead process and records error state."""
        mock_proc = _make_mock_process(alive=False, returncode=1)
        manager._processes[employee_id] = mock_proc
        manager._health_ports[employee_id] = 9100
        manager._tenant_ids[employee_id] = uuid4()

        result = manager.get_status(employee_id)

        assert result["is_running"] is False
        assert result["has_error"] is True
        assert employee_id not in manager._processes


# ============================================================================
# Test: _prune_dead_process
# ============================================================================


class TestPruneDeadProcess:
    """Tests for _prune_dead_process."""

    def test_prune_dead_noop_for_untracked(self, manager, employee_id):
        """Does nothing for untracked employee."""
        manager._prune_dead_process(employee_id)
        # No error

    def test_prune_dead_noop_for_alive(self, manager, employee_id):
        """Does nothing for alive process."""
        mock_proc = _make_mock_process(alive=True)
        manager._processes[employee_id] = mock_proc

        manager._prune_dead_process(employee_id)
        assert employee_id in manager._processes

    def test_prune_dead_cleans_up_exited_with_error(self, manager, employee_id):
        """Cleans up exited process with non-zero return code."""
        mock_proc = _make_mock_process(alive=False, returncode=137)
        manager._processes[employee_id] = mock_proc
        manager._health_ports[employee_id] = 9100
        manager._tenant_ids[employee_id] = uuid4()

        manager._prune_dead_process(employee_id)

        assert employee_id not in manager._processes
        assert employee_id not in manager._health_ports
        assert employee_id not in manager._tenant_ids
        assert manager._error_states[employee_id] == "Process exited with code 137"

    def test_prune_dead_clean_exit_no_error_state(self, manager, employee_id):
        """Clean exit (code 0) does not record error state."""
        mock_proc = _make_mock_process(alive=False, returncode=0)
        manager._processes[employee_id] = mock_proc

        manager._prune_dead_process(employee_id)

        assert employee_id not in manager._processes
        assert employee_id not in manager._error_states


# ============================================================================
# Test: get_health
# ============================================================================


class TestGetHealth:
    """Tests for get_health."""

    @pytest.mark.asyncio
    async def test_get_health_no_port(self, manager, employee_id):
        """Returns None if no health port registered."""
        result = await manager.get_health(employee_id)
        assert result is None

    @pytest.mark.asyncio
    async def test_get_health_success(self, manager, employee_id):
        """Returns health data on successful response."""
        manager._health_ports[employee_id] = 9100

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "healthy", "cycles": 10}

        with patch("empla.services.employee_manager.httpx.AsyncClient") as client_cls:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            client_cls.return_value = mock_client

            result = await manager.get_health(employee_id)
            assert result == {"status": "healthy", "cycles": 10}

    @pytest.mark.asyncio
    async def test_get_health_non_200(self, manager, employee_id):
        """Returns None on non-200 response."""
        manager._health_ports[employee_id] = 9100

        mock_response = Mock()
        mock_response.status_code = 500

        with patch("empla.services.employee_manager.httpx.AsyncClient") as client_cls:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            client_cls.return_value = mock_client

            result = await manager.get_health(employee_id)
            assert result is None

    @pytest.mark.asyncio
    async def test_get_health_connect_error(self, manager, employee_id):
        """Returns None on connection error."""
        manager._health_ports[employee_id] = 9100

        with patch("empla.services.employee_manager.httpx.AsyncClient") as client_cls:
            mock_client = AsyncMock()
            mock_client.get.side_effect = httpx.ConnectError("refused")
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            client_cls.return_value = mock_client

            result = await manager.get_health(employee_id)
            assert result is None

    @pytest.mark.asyncio
    async def test_get_health_timeout(self, manager, employee_id):
        """Returns None on timeout."""
        manager._health_ports[employee_id] = 9100

        with patch("empla.services.employee_manager.httpx.AsyncClient") as client_cls:
            mock_client = AsyncMock()
            mock_client.get.side_effect = httpx.TimeoutException("timed out")
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            client_cls.return_value = mock_client

            result = await manager.get_health(employee_id)
            assert result is None

    @pytest.mark.asyncio
    async def test_get_health_http_error(self, manager, employee_id):
        """Returns None on generic HTTP error."""
        manager._health_ports[employee_id] = 9100

        with patch("empla.services.employee_manager.httpx.AsyncClient") as client_cls:
            mock_client = AsyncMock()
            mock_client.get.side_effect = httpx.HTTPError("generic error")
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            client_cls.return_value = mock_client

            result = await manager.get_health(employee_id)
            assert result is None


# ============================================================================
# Test: list_running
# ============================================================================


class TestListRunning:
    """Tests for list_running."""

    def test_list_running_empty(self, manager):
        """Returns empty list when nothing running."""
        assert manager.list_running() == []

    def test_list_running_with_alive_processes(self, manager):
        """Returns IDs of alive processes."""
        id1, id2 = uuid4(), uuid4()
        manager._processes[id1] = _make_mock_process(alive=True)
        manager._processes[id2] = _make_mock_process(alive=True)

        result = manager.list_running()
        assert set(result) == {id1, id2}

    def test_list_running_prunes_dead(self, manager):
        """Prunes dead processes from listing."""
        alive_id = uuid4()
        dead_id = uuid4()
        manager._processes[alive_id] = _make_mock_process(alive=True)
        manager._processes[dead_id] = _make_mock_process(alive=False, returncode=1)

        result = manager.list_running()
        assert result == [alive_id]
        assert dead_id not in manager._processes


# ============================================================================
# Test: is_running
# ============================================================================


class TestIsRunning:
    """Tests for is_running."""

    def test_is_running_false_not_tracked(self, manager, employee_id):
        """Returns False for untracked employee."""
        assert manager.is_running(employee_id) is False

    def test_is_running_true_alive(self, manager, employee_id):
        """Returns True for alive process."""
        manager._processes[employee_id] = _make_mock_process(alive=True)
        assert manager.is_running(employee_id) is True

    def test_is_running_false_dead(self, manager, employee_id):
        """Returns False for dead process."""
        manager._processes[employee_id] = _make_mock_process(alive=False)
        assert manager.is_running(employee_id) is False


# ============================================================================
# Test: get_health_port
# ============================================================================


class TestGetHealthPort:
    """Tests for get_health_port."""

    def test_returns_port(self, manager, employee_id):
        """Returns health port when set."""
        manager._health_ports[employee_id] = 9100
        assert manager.get_health_port(employee_id) == 9100

    def test_returns_none_when_not_set(self, manager, employee_id):
        """Returns None when no port assigned."""
        assert manager.get_health_port(employee_id) is None


# ============================================================================
# Test: stop_all
# ============================================================================


class TestStopAll:
    """Tests for stop_all."""

    @pytest.mark.asyncio
    async def test_stop_all_empty(self, manager):
        """stop_all with no processes returns empty lists."""
        result = await manager.stop_all()
        assert result == {"stopped": [], "failed": []}

    @pytest.mark.asyncio
    async def test_stop_all_success(self, manager):
        """stop_all stops all tracked processes."""
        id1, id2 = uuid4(), uuid4()
        manager._processes[id1] = _make_mock_process(alive=False, returncode=0)
        manager._processes[id2] = _make_mock_process(alive=False, returncode=0)
        manager._tenant_ids[id1] = uuid4()
        manager._tenant_ids[id2] = uuid4()

        result = await manager.stop_all()
        assert set(result["stopped"]) == {id1, id2}
        assert result["failed"] == []

    @pytest.mark.asyncio
    async def test_stop_all_partial_failure(self, manager):
        """stop_all records failures without crashing."""
        id1, id2 = uuid4(), uuid4()
        # id1 is tracked but will fail (not in processes when stop_employee checks)
        manager._processes[id1] = _make_mock_process(alive=False, returncode=0)
        manager._processes[id2] = _make_mock_process(alive=False, returncode=0)
        manager._tenant_ids[id2] = uuid4()

        # Make stop_employee raise for id1 by not having it in tenant_ids but providing session
        result = await manager.stop_all(session=AsyncMock())

        # Both should appear in either stopped or failed
        total = len(result["stopped"]) + len(result["failed"])
        assert total == 2


# ============================================================================
# Test: _get_lock
# ============================================================================


class TestGetLock:
    """Tests for _get_lock."""

    @pytest.mark.asyncio
    async def test_get_lock_creates_lock(self, manager):
        """Creates a lock on first access."""
        manager._lock = None
        lock = await manager._get_lock()
        assert isinstance(lock, asyncio.Lock)

    @pytest.mark.asyncio
    async def test_get_lock_returns_same_lock(self, manager):
        """Returns the same lock on subsequent calls."""
        lock1 = await manager._get_lock()
        lock2 = await manager._get_lock()
        assert lock1 is lock2


# ============================================================================
# Test: UnsupportedRoleError
# ============================================================================


class TestUnsupportedRoleError:
    """Tests for UnsupportedRoleError."""

    def test_is_value_error(self):
        """UnsupportedRoleError is a ValueError subclass."""
        assert issubclass(UnsupportedRoleError, ValueError)

    def test_message(self):
        """Can be raised with a message."""
        with pytest.raises(UnsupportedRoleError, match="bad role"):
            raise UnsupportedRoleError("bad role")
