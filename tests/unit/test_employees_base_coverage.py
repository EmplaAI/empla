"""
Extended coverage tests for empla.employees.base module.

Focuses on lifecycle methods (start/stop), initialization helpers,
error paths, and component wiring that the existing test_employees_base.py
doesn't cover.
"""

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, Mock, patch
from uuid import uuid4

import pytest

from empla.employees.base import DigitalEmployee, MemorySystem
from empla.employees.config import EmployeeConfig, GoalConfig
from empla.employees.exceptions import (
    EmployeeConfigError,
    EmployeeNotStartedError,
    EmployeeStartupError,
)
from empla.employees.personality import Personality

# ============================================================================
# Concrete subclass for testing
# ============================================================================


class ConcreteEmployee(DigitalEmployee):
    """Concrete implementation for testing the abstract base class."""

    def __init__(self, config: EmployeeConfig, on_start_side_effect: Exception | None = None):
        super().__init__(config)
        self._on_start_side_effect = on_start_side_effect
        self.on_start_called = False
        self.on_stop_called = False

    @property
    def default_personality(self) -> Personality:
        return Personality(extraversion=0.7, conscientiousness=0.8)

    @property
    def default_goals(self) -> list[GoalConfig]:
        return [
            GoalConfig(description="Test goal", priority=5),
            GoalConfig(description="Secondary goal", priority=3),
        ]

    @property
    def default_capabilities(self) -> list[str]:
        return ["email", "calendar"]

    async def on_start(self) -> None:
        self.on_start_called = True
        if self._on_start_side_effect:
            raise self._on_start_side_effect

    async def on_stop(self) -> None:
        self.on_stop_called = True


def _make_config(**overrides) -> EmployeeConfig:
    """Helper to create EmployeeConfig with sensible defaults."""
    defaults = {
        "name": "Test Employee",
        "role": "custom",
        "email": "test@test.com",
        "tenant_id": uuid4(),
    }
    defaults.update(overrides)
    return EmployeeConfig(**defaults)


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def config():
    return _make_config()


@pytest.fixture
def employee(config):
    return ConcreteEmployee(config)


def _make_mock_session():
    """Create a mock async session with common query patterns.

    session.execute/flush/commit/close are async (awaited in code).
    session.add is sync (not awaited in code).
    The result of session.execute() has sync methods like scalar_one_or_none().
    """
    session = AsyncMock()
    mock_result = Mock()
    mock_result.scalar_one_or_none.return_value = None
    session.execute.return_value = mock_result
    # add() is sync in SQLAlchemy — use a plain Mock to avoid unawaited coroutine
    session.add = Mock()
    return session


def _make_mock_engine():
    engine = AsyncMock()
    engine.dispose = AsyncMock()
    return engine


def _make_mock_sessionmaker(session):
    """Create a sessionmaker that returns the given session when called."""
    sm = MagicMock()
    sm.return_value = session
    return sm


def _make_mock_settings(has_llm: bool = True):
    """Create mock settings."""
    settings = Mock()
    settings.has_llm_credentials.return_value = has_llm
    return settings


# ============================================================================
# Test: MemorySystem
# ============================================================================


class TestMemorySystemInit:
    """Tests for MemorySystem container initialization."""

    def test_memory_system_creates_all_subsystems(self):
        """MemorySystem should create episodic, semantic, procedural, working."""
        session = AsyncMock()
        employee_id = uuid4()
        tenant_id = uuid4()

        with (
            patch("empla.employees.base.EpisodicMemorySystem") as ep_mock,
            patch("empla.employees.base.SemanticMemorySystem") as sem_mock,
            patch("empla.employees.base.ProceduralMemorySystem") as proc_mock,
            patch("empla.employees.base.WorkingMemory") as wm_mock,
        ):
            mem = MemorySystem(session, employee_id, tenant_id)

            ep_mock.assert_called_once_with(session, employee_id, tenant_id)
            sem_mock.assert_called_once_with(session, employee_id, tenant_id)
            proc_mock.assert_called_once_with(session, employee_id, tenant_id)
            wm_mock.assert_called_once_with(session, employee_id, tenant_id)

            assert mem.episodic == ep_mock.return_value
            assert mem.semantic == sem_mock.return_value
            assert mem.procedural == proc_mock.return_value
            assert mem.working == wm_mock.return_value


# ============================================================================
# Test: Properties - additional coverage
# ============================================================================


class TestPropertiesAdditional:
    """Additional property tests not covered by existing tests."""

    def test_get_status_uses_default_capabilities_when_config_empty(self):
        """get_status falls back to default_capabilities when config has none."""
        config = _make_config(capabilities=[])
        emp = ConcreteEmployee(config)
        status = emp.get_status()
        # Empty list from config => uses default_capabilities
        # Actually, the config.capabilities is [] which is falsy
        # so it falls back to default_capabilities
        assert status["capabilities"] == ["email", "calendar"]

    def test_get_status_with_employee_id_set(self):
        """get_status returns stringified UUID when employee started."""
        config = _make_config()
        emp = ConcreteEmployee(config)
        eid = uuid4()
        emp._employee_id = eid
        emp._is_running = True
        emp._started_at = datetime(2025, 1, 1, tzinfo=UTC)

        status = emp.get_status()
        assert status["employee_id"] == str(eid)
        assert status["is_running"] is True
        assert status["started_at"] == "2025-01-01T00:00:00+00:00"

    def test_repr_running(self):
        """repr shows 'running' when _is_running is True."""
        emp = ConcreteEmployee(_make_config())
        emp._is_running = True
        r = repr(emp)
        assert "running" in r
        assert "ConcreteEmployee" in r

    def test_hooks_property_returns_hook_registry(self):
        """hooks property returns the HookRegistry directly."""
        emp = ConcreteEmployee(_make_config())
        assert emp.hooks is emp._hooks


# ============================================================================
# Test: _validate_config
# ============================================================================


class TestValidateConfig:
    """Tests for the _validate_config method."""

    @pytest.mark.asyncio
    async def test_validate_config_passes_with_credentials(self, employee):
        """_validate_config succeeds when LLM credentials are present."""
        mock_settings = _make_mock_settings(has_llm=True)
        with patch("empla.settings.get_settings", return_value=mock_settings):
            await employee._validate_config()  # Should not raise

    @pytest.mark.asyncio
    async def test_validate_config_raises_without_credentials(self, employee):
        """_validate_config raises EmployeeConfigError without LLM keys."""
        mock_settings = _make_mock_settings(has_llm=False)
        with patch("empla.settings.get_settings", return_value=mock_settings):
            with pytest.raises(EmployeeConfigError, match="No LLM credentials"):
                await employee._validate_config()


# ============================================================================
# Test: _cleanup_on_error
# ============================================================================


class TestCleanupOnError:
    """Tests for the _cleanup_on_error method."""

    @pytest.mark.asyncio
    async def test_cleanup_closes_session_and_engine(self, employee):
        """_cleanup_on_error closes session and disposes engine."""
        session = AsyncMock()
        engine = _make_mock_engine()
        employee._session = session
        employee._engine = engine
        employee._sessionmaker = MagicMock()
        employee._is_running = True

        await employee._cleanup_on_error()

        session.close.assert_awaited_once()
        engine.dispose.assert_awaited_once()
        assert employee._session is None
        assert employee._engine is None
        assert employee._sessionmaker is None
        assert employee._is_running is False

    @pytest.mark.asyncio
    async def test_cleanup_stops_loop(self, employee):
        """_cleanup_on_error stops the loop if present."""
        mock_loop = AsyncMock()
        employee._loop = mock_loop

        await employee._cleanup_on_error()

        mock_loop.stop.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_cleanup_disconnects_mcp_bridge(self, employee):
        """_cleanup_on_error disconnects MCP servers."""
        mock_bridge = AsyncMock()
        employee._mcp_bridge = mock_bridge

        await employee._cleanup_on_error()

        mock_bridge.disconnect_all.assert_awaited_once()
        assert employee._mcp_bridge is None

    @pytest.mark.asyncio
    async def test_cleanup_clears_tool_state(self, employee):
        """_cleanup_on_error clears tool registry and router."""
        employee._tool_registry = Mock()
        employee._tool_router = Mock()

        await employee._cleanup_on_error()

        assert employee._tool_registry is None
        assert employee._tool_router is None

    @pytest.mark.asyncio
    async def test_cleanup_handles_loop_stop_error(self, employee):
        """_cleanup_on_error handles errors in loop.stop()."""
        mock_loop = AsyncMock()
        mock_loop.stop.side_effect = RuntimeError("loop stop failed")
        employee._loop = mock_loop

        # Should not raise
        await employee._cleanup_on_error()

    @pytest.mark.asyncio
    async def test_cleanup_handles_session_close_error(self, employee):
        """_cleanup_on_error handles errors in session.close()."""
        session = AsyncMock()
        session.close.side_effect = RuntimeError("close failed")
        employee._session = session

        await employee._cleanup_on_error()
        assert employee._session is None

    @pytest.mark.asyncio
    async def test_cleanup_handles_engine_dispose_error(self, employee):
        """_cleanup_on_error handles errors in engine.dispose()."""
        engine = AsyncMock()
        engine.dispose.side_effect = RuntimeError("dispose failed")
        employee._engine = engine
        employee._sessionmaker = MagicMock()

        await employee._cleanup_on_error()
        assert employee._engine is None
        assert employee._sessionmaker is None

    @pytest.mark.asyncio
    async def test_cleanup_handles_mcp_disconnect_error(self, employee):
        """_cleanup_on_error handles errors in mcp_bridge.disconnect_all()."""
        mock_bridge = AsyncMock()
        mock_bridge.disconnect_all.side_effect = RuntimeError("disconnect failed")
        employee._mcp_bridge = mock_bridge

        await employee._cleanup_on_error()
        assert employee._mcp_bridge is None

    @pytest.mark.asyncio
    async def test_cleanup_with_nothing_initialized(self, employee):
        """_cleanup_on_error works when nothing has been initialized."""
        await employee._cleanup_on_error()
        assert employee._is_running is False


# ============================================================================
# Test: _init_employee_record
# ============================================================================


class TestInitEmployeeRecord:
    """Tests for _init_employee_record."""

    @pytest.mark.asyncio
    async def test_creates_new_employee_when_not_found(self, employee):
        """Creates new DB record when no matching employee exists."""
        session = _make_mock_session()

        mock_instance = Mock()
        mock_instance.id = uuid4()

        with (
            patch("empla.employees.base.select") as mock_select,
            patch("empla.employees.base.EmployeeModel") as model_cls,
        ):
            mock_select.return_value.where.return_value = "fake_query"
            model_cls.return_value = mock_instance

            await employee._init_employee_record(session)

            model_cls.assert_called_once()
            session.add.assert_called_once_with(mock_instance)
            session.flush.assert_awaited_once()
            assert employee._employee_id == mock_instance.id

    @pytest.mark.asyncio
    async def test_reuses_existing_employee(self, employee):
        """Reuses existing DB record when one is found."""
        session = _make_mock_session()

        existing = Mock()
        existing.id = uuid4()
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = existing
        session.execute.return_value = mock_result

        with patch("empla.employees.base.select") as mock_select:
            mock_select.return_value.where.return_value = "fake_query"

            await employee._init_employee_record(session)

            assert employee._employee_id == existing.id
            assert employee._db_employee is existing
            assert existing.status == "active"
            session.add.assert_not_called()


# ============================================================================
# Test: _init_llm
# ============================================================================


class TestInitLLM:
    """Tests for _init_llm."""

    @pytest.mark.asyncio
    async def test_init_llm_creates_service(self, employee):
        """_init_llm creates LLMService from settings."""
        mock_settings = _make_mock_settings(has_llm=True)
        mock_config = Mock()

        with (
            patch("empla.settings.get_settings", return_value=mock_settings),
            patch("empla.settings.resolve_llm_config", return_value=mock_config) as resolve,
            patch("empla.employees.base.LLMService") as llm_cls,
        ):
            await employee._init_llm()

            resolve.assert_called_once_with(
                server_settings=mock_settings,
                employee_llm=employee.config.llm,
            )
            llm_cls.assert_called_once_with(mock_config)
            assert employee._llm == llm_cls.return_value

    @pytest.mark.asyncio
    async def test_init_llm_raises_without_credentials(self, employee):
        """_init_llm raises EmployeeConfigError if no LLM credentials."""
        mock_settings = _make_mock_settings(has_llm=False)

        with patch("empla.settings.get_settings", return_value=mock_settings):
            with pytest.raises(EmployeeConfigError, match="No LLM credentials"):
                await employee._init_llm()


# ============================================================================
# Test: _init_bdi
# ============================================================================


class TestInitBDI:
    """Tests for _init_bdi."""

    @pytest.mark.asyncio
    async def test_init_bdi_creates_all_components(self, employee):
        """_init_bdi creates beliefs, goals, intentions."""
        session = AsyncMock()
        employee._employee_id = uuid4()
        employee._llm = Mock()

        with (
            patch("empla.employees.base.BeliefSystem") as belief_cls,
            patch("empla.employees.base.GoalSystem") as goal_cls,
            patch("empla.employees.base.IntentionStack") as intent_cls,
        ):
            await employee._init_bdi(session)

            belief_cls.assert_called_once_with(
                session=session,
                employee_id=employee.employee_id,
                tenant_id=employee.tenant_id,
                llm_service=employee._llm,
            )
            goal_cls.assert_called_once_with(
                session=session,
                employee_id=employee.employee_id,
                tenant_id=employee.tenant_id,
            )
            intent_cls.assert_called_once_with(
                session=session,
                employee_id=employee.employee_id,
                tenant_id=employee.tenant_id,
            )
            assert employee._beliefs == belief_cls.return_value
            assert employee._goals == goal_cls.return_value
            assert employee._intentions == intent_cls.return_value


# ============================================================================
# Test: _init_memory
# ============================================================================


class TestInitMemory:
    """Tests for _init_memory."""

    @pytest.mark.asyncio
    async def test_init_memory_creates_memory_system(self, employee):
        """_init_memory creates MemorySystem."""
        session = AsyncMock()
        employee._employee_id = uuid4()

        with patch("empla.employees.base.MemorySystem") as mem_cls:
            await employee._init_memory(session)

            mem_cls.assert_called_once_with(
                session=session,
                employee_id=employee.employee_id,
                tenant_id=employee.tenant_id,
            )
            assert employee._memory == mem_cls.return_value


# ============================================================================
# Test: _create_default_goals
# ============================================================================


class TestCreateDefaultGoals:
    """Tests for _create_default_goals."""

    @pytest.mark.asyncio
    async def test_creates_goals_when_none_exist(self, employee):
        """Creates default goals when no existing goals."""
        employee._goals = AsyncMock()
        employee._goals.get_pursuing_goals.return_value = []

        await employee._create_default_goals()

        assert employee._goals.add_goal.await_count == 2  # Two default goals

    @pytest.mark.asyncio
    async def test_skips_duplicate_goals(self, employee):
        """Skips goals that already exist (by description)."""
        employee._goals = AsyncMock()
        existing_goal = Mock()
        existing_goal.description = "Test goal"
        employee._goals.get_pursuing_goals.return_value = [existing_goal]

        await employee._create_default_goals()

        # Only "Secondary goal" should be created; "Test goal" is skipped
        assert employee._goals.add_goal.await_count == 1

    @pytest.mark.asyncio
    async def test_uses_config_goals_over_defaults(self, employee):
        """Uses goals from config when provided."""
        config = _make_config(goals=[GoalConfig(description="Config goal", priority=8)])
        emp = ConcreteEmployee(config)
        emp._goals = AsyncMock()
        emp._goals.get_pursuing_goals.return_value = []

        await emp._create_default_goals()

        assert emp._goals.add_goal.await_count == 1
        call_kwargs = emp._goals.add_goal.call_args.kwargs
        assert call_kwargs["description"] == "Config goal"
        assert call_kwargs["priority"] == 8


# ============================================================================
# Test: _build_identity
# ============================================================================


class TestBuildIdentity:
    """Tests for _build_identity."""

    def test_build_identity_returns_identity(self, employee):
        """_build_identity constructs an EmployeeIdentity."""
        with patch("empla.employees.base.EmployeeIdentity") as id_cls:
            mock_build = Mock()
            id_cls.build = mock_build

            result = employee._build_identity()

            mock_build.assert_called_once()
            call_kwargs = mock_build.call_args.kwargs
            assert call_kwargs["name"] == employee.config.name
            assert call_kwargs["role"] == employee.config.role
            assert result == mock_build.return_value


# ============================================================================
# Test: _init_loop
# ============================================================================


class TestInitLoop:
    """Tests for _init_loop."""

    @pytest.mark.asyncio
    async def test_init_loop_creates_components(self, employee):
        """_init_loop creates tool registry, router, and loop."""
        employee._employee_id = uuid4()
        employee._db_employee = Mock()
        employee._beliefs = Mock()
        employee._goals = Mock()
        employee._intentions = Mock()
        employee._memory = Mock()
        employee._llm = Mock()
        employee._session = AsyncMock()
        # Sentinel sessionmaker — must be forwarded to ProactiveExecutionLoop.
        # This test guards against the class of bug PR #77 fixed: the loop used
        # to read sessionmaker via ``getattr(self.employee, "_sessionmaker", None)``
        # where ``self.employee`` was the ORM row (not the DigitalEmployee),
        # so the getattr always returned None and metrics silently no-op'd.
        # If a future refactor drops the ``sessionmaker=`` kwarg from base.py,
        # this assertion fails — production metrics would silently break again
        # otherwise.
        sentinel_sessionmaker = Mock(name="sentinel_sessionmaker")
        employee._sessionmaker = sentinel_sessionmaker

        with (
            patch("empla.employees.base.ToolRegistry") as tr_cls,
            patch("empla.employees.base.ToolRouter") as router_cls,
            patch("empla.employees.base.ProactiveExecutionLoop") as loop_cls,
            patch("empla.employees.base.ActivityRecorder") as ar_cls,
            patch.object(employee, "_build_identity", return_value=Mock()),
        ):
            await employee._init_loop()

            tr_cls.assert_called_once()
            router_cls.assert_called_once_with(tr_cls.return_value)
            loop_cls.assert_called_once()
            # Verify sessionmaker was explicitly forwarded (regression guard for #77).
            assert loop_cls.call_args.kwargs.get("sessionmaker") is sentinel_sessionmaker, (
                "ProactiveExecutionLoop must receive sessionmaker via the explicit "
                "sessionmaker= kwarg. If this fails, cycle metrics will silently "
                "no-op in production. See PR #77."
            )
            ar_cls.assert_called_once()
            assert employee._tool_registry == tr_cls.return_value
            assert employee._tool_router == router_cls.return_value
            assert employee._loop == loop_cls.return_value

    @pytest.mark.asyncio
    async def test_init_loop_reuses_existing_tool_registry(self, employee):
        """_init_loop reuses existing ToolRegistry from MCP init."""
        employee._employee_id = uuid4()
        employee._db_employee = Mock()
        employee._beliefs = Mock()
        employee._goals = Mock()
        employee._intentions = Mock()
        employee._memory = Mock()
        employee._llm = Mock()
        employee._session = AsyncMock()
        existing_registry = Mock()
        employee._tool_registry = existing_registry

        with (
            patch("empla.employees.base.ToolRegistry") as tr_cls,
            patch("empla.employees.base.ToolRouter"),
            patch("empla.employees.base.ProactiveExecutionLoop"),
            patch("empla.employees.base.ActivityRecorder"),
            patch.object(employee, "_build_identity", return_value=Mock()),
        ):
            await employee._init_loop()

            # ToolRegistry() should NOT be called since we already have one
            tr_cls.assert_not_called()
            assert employee._tool_registry is existing_registry

    @pytest.mark.asyncio
    async def test_init_loop_handles_identity_build_failure(self, employee):
        """_init_loop handles identity build failure gracefully."""
        employee._employee_id = uuid4()
        employee._db_employee = Mock()
        employee._beliefs = Mock()
        employee._goals = Mock()
        employee._intentions = Mock()
        employee._memory = Mock()
        employee._llm = Mock()
        employee._session = AsyncMock()

        with (
            patch("empla.employees.base.ToolRegistry"),
            patch("empla.employees.base.ToolRouter"),
            patch("empla.employees.base.ProactiveExecutionLoop") as loop_cls,
            patch("empla.employees.base.ActivityRecorder"),
            patch.object(employee, "_build_identity", side_effect=ValueError("bad identity")),
        ):
            await employee._init_loop()

            # Loop should still be created, but identity=None
            call_kwargs = loop_cls.call_args.kwargs
            assert call_kwargs["identity"] is None


# ============================================================================
# Test: _init_mcp_servers
# ============================================================================


class TestInitMCPServers:
    """Tests for _init_mcp_servers."""

    @pytest.mark.asyncio
    async def test_init_mcp_servers_empty_list(self, employee):
        """_init_mcp_servers with empty list does nothing."""
        await employee._init_mcp_servers([])
        assert employee._mcp_bridge is None

    @pytest.mark.asyncio
    async def test_init_mcp_servers_creates_bridge(self, employee):
        """_init_mcp_servers creates MCPBridge and connects."""
        mock_config = Mock()
        mock_config.name = "test-server"

        with (
            patch("empla.employees.base.ToolRegistry") as tr_cls,
            patch("empla.employees.base.MCPBridge") as bridge_cls,
        ):
            mock_bridge = AsyncMock()
            mock_bridge.connect.return_value = ["tool1", "tool2"]
            bridge_cls.return_value = mock_bridge

            await employee._init_mcp_servers([mock_config])

            bridge_cls.assert_called_once_with(tr_cls.return_value)
            mock_bridge.connect.assert_awaited_once_with(mock_config)
            assert employee._mcp_bridge is mock_bridge

    @pytest.mark.asyncio
    async def test_init_mcp_servers_handles_connection_failure(self, employee):
        """Failed MCP connections are logged, not raised."""
        mock_config = Mock()
        mock_config.name = "failing-server"

        with (
            patch("empla.employees.base.ToolRegistry"),
            patch("empla.employees.base.MCPBridge") as bridge_cls,
        ):
            mock_bridge = AsyncMock()
            mock_bridge.connect.side_effect = ConnectionError("refused")
            bridge_cls.return_value = mock_bridge

            # Should not raise
            await employee._init_mcp_servers([mock_config])

    @pytest.mark.asyncio
    async def test_init_mcp_servers_reuses_existing_registry(self, employee):
        """Uses existing _tool_registry if already set."""
        existing_registry = Mock()
        employee._tool_registry = existing_registry
        mock_config = Mock()
        mock_config.name = "test"

        with (
            patch("empla.employees.base.ToolRegistry") as tr_cls,
            patch("empla.employees.base.MCPBridge") as bridge_cls,
        ):
            mock_bridge = AsyncMock()
            mock_bridge.connect.return_value = []
            bridge_cls.return_value = mock_bridge

            await employee._init_mcp_servers([mock_config])

            # Should NOT create a new ToolRegistry
            tr_cls.assert_not_called()
            bridge_cls.assert_called_once_with(existing_registry)


# ============================================================================
# Test: start() lifecycle
# ============================================================================


class TestStartLifecycle:
    """Tests for the start() method."""

    @pytest.mark.asyncio
    async def test_start_already_running_returns_early(self, employee):
        """start() returns immediately if already running."""
        employee._is_running = True

        # Should not raise and not call any init methods
        await employee.start(run_loop=False)

    @pytest.mark.asyncio
    async def test_start_initializes_all_components(self):
        """start(run_loop=False) initializes all components."""
        config = _make_config()
        emp = ConcreteEmployee(config)

        session = _make_mock_session()
        engine = _make_mock_engine()
        sm = _make_mock_sessionmaker(session)

        mock_settings = _make_mock_settings(has_llm=True)

        with (
            patch("empla.settings.get_settings", return_value=mock_settings),
            patch("empla.employees.base.get_engine", return_value=engine),
            patch("empla.employees.base.get_sessionmaker", return_value=sm),
            patch.object(emp, "_init_employee_record", new_callable=AsyncMock) as init_rec,
            patch.object(emp, "_init_llm", new_callable=AsyncMock) as init_llm,
            patch.object(emp, "_init_bdi", new_callable=AsyncMock) as init_bdi,
            patch.object(emp, "_init_memory", new_callable=AsyncMock) as init_mem,
            patch.object(emp, "_create_default_goals", new_callable=AsyncMock) as init_goals,
            patch.object(emp, "_init_loop", new_callable=AsyncMock) as init_loop,
        ):
            emp._employee_id = uuid4()  # Simulate _init_employee_record setting this

            await emp.start(run_loop=False)

            init_rec.assert_awaited_once()
            init_llm.assert_awaited_once()
            init_bdi.assert_awaited_once()
            init_mem.assert_awaited_once()
            init_goals.assert_awaited_once()
            init_loop.assert_awaited_once()

            assert emp._is_running is True
            assert emp._started_at is not None
            assert emp.on_start_called is True
            session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_start_on_start_failure_cleans_up(self):
        """start() cleans up if on_start() raises."""
        config = _make_config()
        emp = ConcreteEmployee(config, on_start_side_effect=RuntimeError("on_start boom"))

        session = _make_mock_session()
        engine = _make_mock_engine()
        sm = _make_mock_sessionmaker(session)
        mock_settings = _make_mock_settings(has_llm=True)

        with (
            patch("empla.settings.get_settings", return_value=mock_settings),
            patch("empla.employees.base.get_engine", return_value=engine),
            patch("empla.employees.base.get_sessionmaker", return_value=sm),
            patch.object(emp, "_init_employee_record", new_callable=AsyncMock),
            patch.object(emp, "_init_llm", new_callable=AsyncMock),
            patch.object(emp, "_init_bdi", new_callable=AsyncMock),
            patch.object(emp, "_init_memory", new_callable=AsyncMock),
            patch.object(emp, "_create_default_goals", new_callable=AsyncMock),
            patch.object(emp, "_init_loop", new_callable=AsyncMock),
            patch.object(emp, "_cleanup_on_error", new_callable=AsyncMock) as cleanup,
        ):
            emp._employee_id = uuid4()

            with pytest.raises(EmployeeStartupError, match="on_start"):
                await emp.start(run_loop=False)

            cleanup.assert_awaited_once()
            assert emp._is_running is False

    @pytest.mark.asyncio
    async def test_start_config_validation_failure(self):
        """start() raises EmployeeConfigError on config validation failure."""
        config = _make_config()
        emp = ConcreteEmployee(config)

        mock_settings = _make_mock_settings(has_llm=False)

        with patch("empla.settings.get_settings", return_value=mock_settings):
            with pytest.raises(EmployeeConfigError, match="No LLM credentials"):
                await emp.start(run_loop=False)

    @pytest.mark.asyncio
    async def test_start_generic_exception_wraps_in_startup_error(self):
        """start() wraps generic exceptions in EmployeeStartupError."""
        config = _make_config()
        emp = ConcreteEmployee(config)

        mock_settings = _make_mock_settings(has_llm=True)

        with (
            patch("empla.settings.get_settings", return_value=mock_settings),
            patch("empla.employees.base.get_engine", side_effect=RuntimeError("db down")),
            patch.object(emp, "_cleanup_on_error", new_callable=AsyncMock) as cleanup,
        ):
            with pytest.raises(EmployeeStartupError, match="Employee initialization failed"):
                await emp.start(run_loop=False)

            cleanup.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_start_with_mcp_configs(self):
        """start() calls _init_mcp_servers when mcp_configs provided."""
        config = _make_config()
        emp = ConcreteEmployee(config)

        session = _make_mock_session()
        engine = _make_mock_engine()
        sm = _make_mock_sessionmaker(session)
        mock_settings = _make_mock_settings(has_llm=True)
        mcp_config = Mock()

        with (
            patch("empla.settings.get_settings", return_value=mock_settings),
            patch("empla.employees.base.get_engine", return_value=engine),
            patch("empla.employees.base.get_sessionmaker", return_value=sm),
            patch.object(emp, "_init_employee_record", new_callable=AsyncMock),
            patch.object(emp, "_init_llm", new_callable=AsyncMock),
            patch.object(emp, "_init_bdi", new_callable=AsyncMock),
            patch.object(emp, "_init_memory", new_callable=AsyncMock),
            patch.object(emp, "_init_mcp_servers", new_callable=AsyncMock) as init_mcp,
            patch.object(emp, "_create_default_goals", new_callable=AsyncMock),
            patch.object(emp, "_init_loop", new_callable=AsyncMock),
        ):
            emp._employee_id = uuid4()

            await emp.start(run_loop=False, mcp_configs=[mcp_config])

            init_mcp.assert_awaited_once_with([mcp_config])

    @pytest.mark.asyncio
    async def test_start_hook_emission_failure_does_not_crash(self):
        """start() continues even if hook emission fails."""
        config = _make_config()
        emp = ConcreteEmployee(config)

        session = _make_mock_session()
        engine = _make_mock_engine()
        sm = _make_mock_sessionmaker(session)
        mock_settings = _make_mock_settings(has_llm=True)

        # Register a hook that will fail
        async def failing_hook(**kwargs):
            raise RuntimeError("hook failure")

        emp._hooks.register("employee_start", failing_hook)

        with (
            patch("empla.settings.get_settings", return_value=mock_settings),
            patch("empla.employees.base.get_engine", return_value=engine),
            patch("empla.employees.base.get_sessionmaker", return_value=sm),
            patch.object(emp, "_init_employee_record", new_callable=AsyncMock),
            patch.object(emp, "_init_llm", new_callable=AsyncMock),
            patch.object(emp, "_init_bdi", new_callable=AsyncMock),
            patch.object(emp, "_init_memory", new_callable=AsyncMock),
            patch.object(emp, "_create_default_goals", new_callable=AsyncMock),
            patch.object(emp, "_init_loop", new_callable=AsyncMock),
        ):
            emp._employee_id = uuid4()

            # Should not raise despite hook failure
            await emp.start(run_loop=False)
            assert emp._is_running is True


# ============================================================================
# Test: stop() lifecycle
# ============================================================================


class TestStopLifecycle:
    """Tests for the stop() method."""

    @pytest.mark.asyncio
    async def test_stop_not_running_returns_early(self, employee):
        """stop() returns immediately if not running."""
        employee._is_running = False
        await employee.stop()  # Should not raise

    @pytest.mark.asyncio
    async def test_stop_cleans_up_all_components(self, employee):
        """stop() cleans up loop, MCP, LLM, session, engine."""
        employee._is_running = True
        mock_loop = AsyncMock()
        mock_bridge = AsyncMock()
        mock_llm = AsyncMock()
        session = AsyncMock()
        engine = _make_mock_engine()

        employee._loop = mock_loop
        employee._mcp_bridge = mock_bridge
        employee._llm = mock_llm
        employee._session = session
        employee._engine = engine
        employee._sessionmaker = MagicMock()
        employee._tool_registry = Mock()
        employee._tool_router = Mock()
        employee._employee_id = uuid4()

        await employee.stop()

        mock_loop.stop.assert_awaited_once()
        mock_bridge.disconnect_all.assert_awaited_once()
        assert employee.on_stop_called is True
        mock_llm.close.assert_awaited_once()
        session.close.assert_awaited_once()
        engine.dispose.assert_awaited_once()

        assert employee._is_running is False
        assert employee._mcp_bridge is None
        assert employee._llm is None
        assert employee._session is None
        assert employee._engine is None
        assert employee._sessionmaker is None
        assert employee._tool_registry is None
        assert employee._tool_router is None

    @pytest.mark.asyncio
    async def test_stop_cancels_loop_task(self, employee):
        """stop() cancels running loop task."""
        employee._is_running = True
        employee._employee_id = uuid4()

        # Create a real task that we can cancel
        async def forever():
            await asyncio.sleep(1000)

        employee._loop_task = asyncio.create_task(forever())
        employee._loop = AsyncMock()

        await employee.stop()

        assert employee._loop_task.cancelled() or employee._loop_task.done()

    @pytest.mark.asyncio
    async def test_stop_handles_loop_stop_error(self, employee):
        """stop() logs but doesn't raise on loop.stop() error."""
        employee._is_running = True
        employee._employee_id = uuid4()
        mock_loop = AsyncMock()
        mock_loop.stop.side_effect = RuntimeError("loop crash")
        employee._loop = mock_loop

        await employee.stop()
        assert employee._is_running is False

    @pytest.mark.asyncio
    async def test_stop_handles_on_stop_error(self):
        """stop() logs but doesn't raise on on_stop() error."""

        class FailingStopEmployee(ConcreteEmployee):
            async def on_stop(self) -> None:
                raise RuntimeError("on_stop boom")

        config = _make_config()
        emp = FailingStopEmployee(config)
        emp._is_running = True
        emp._employee_id = uuid4()

        await emp.stop()
        assert emp._is_running is False

    @pytest.mark.asyncio
    async def test_stop_handles_llm_close_error(self, employee):
        """stop() logs but doesn't raise on LLM close error."""
        employee._is_running = True
        employee._employee_id = uuid4()
        mock_llm = AsyncMock()
        mock_llm.close.side_effect = RuntimeError("llm close failed")
        employee._llm = mock_llm

        await employee.stop()
        assert employee._is_running is False
        assert employee._llm is None

    @pytest.mark.asyncio
    async def test_stop_handles_session_close_error(self, employee):
        """stop() logs but doesn't raise on session close error."""
        employee._is_running = True
        employee._employee_id = uuid4()
        session = AsyncMock()
        session.close.side_effect = RuntimeError("session close failed")
        employee._session = session

        await employee.stop()
        assert employee._is_running is False
        assert employee._session is None

    @pytest.mark.asyncio
    async def test_stop_handles_engine_dispose_error(self, employee):
        """stop() logs but doesn't raise on engine dispose error."""
        employee._is_running = True
        employee._employee_id = uuid4()
        engine = AsyncMock()
        engine.dispose.side_effect = RuntimeError("dispose failed")
        employee._engine = engine
        employee._sessionmaker = MagicMock()

        await employee.stop()
        assert employee._is_running is False
        assert employee._engine is None
        assert employee._sessionmaker is None

    @pytest.mark.asyncio
    async def test_stop_hook_emission_failure_does_not_crash(self, employee):
        """stop() continues even if hook emission fails."""
        employee._is_running = True
        employee._employee_id = uuid4()

        async def failing_hook(**kwargs):
            raise RuntimeError("hook failure")

        employee._hooks.register("employee_stop", failing_hook)

        await employee.stop()
        assert employee._is_running is False

    @pytest.mark.asyncio
    async def test_stop_mcp_disconnect_error(self, employee):
        """stop() handles MCP disconnect error."""
        employee._is_running = True
        employee._employee_id = uuid4()
        mock_bridge = AsyncMock()
        mock_bridge.disconnect_all.side_effect = RuntimeError("mcp error")
        employee._mcp_bridge = mock_bridge

        await employee.stop()
        assert employee._is_running is False
        assert employee._mcp_bridge is None


# ============================================================================
# Test: run_once
# ============================================================================


class TestRunOnce:
    """Tests for the run_once() method."""

    @pytest.mark.asyncio
    async def test_run_once_raises_when_not_started(self, employee):
        """run_once() raises EmployeeNotStartedError when not running."""
        with pytest.raises(EmployeeNotStartedError, match="call start"):
            await employee.run_once()

    @pytest.mark.asyncio
    async def test_run_once_calls_loop_run_cycle(self, employee):
        """run_once() delegates to loop._run_cycle()."""
        employee._is_running = True
        mock_loop = AsyncMock()
        employee._loop = mock_loop

        await employee.run_once()

        mock_loop._run_cycle.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_run_once_noop_without_loop(self, employee):
        """run_once() does nothing if loop is None but employee is running."""
        employee._is_running = True
        employee._loop = None

        # Should not raise
        await employee.run_once()


# ============================================================================
# Test: _run_loop
# ============================================================================


class TestRunLoop:
    """Tests for the _run_loop() method."""

    @pytest.mark.asyncio
    async def test_run_loop_creates_task(self, employee):
        """_run_loop() creates an asyncio task for the loop."""
        mock_loop = AsyncMock()
        # Make start() resolve immediately
        mock_loop.start = AsyncMock()
        employee._loop = mock_loop

        await employee._run_loop()

        mock_loop.start.assert_awaited_once()
        assert employee._loop_task is not None

    @pytest.mark.asyncio
    async def test_run_loop_handles_cancelled(self, employee):
        """_run_loop() handles CancelledError from the loop task."""
        mock_loop = AsyncMock()
        mock_loop.start.side_effect = asyncio.CancelledError()
        employee._loop = mock_loop

        # Should not raise
        await employee._run_loop()

    @pytest.mark.asyncio
    async def test_run_loop_noop_without_loop(self, employee):
        """_run_loop() does nothing if loop is None."""
        employee._loop = None
        await employee._run_loop()
        assert employee._loop_task is None


# ============================================================================
# Test: on_start / on_stop default implementations
# ============================================================================


class TestDefaultHooks:
    """Tests for default on_start/on_stop implementations."""

    @pytest.mark.asyncio
    async def test_default_on_start_is_noop(self):
        """Default on_start() does nothing."""

        class MinimalEmployee(DigitalEmployee):
            @property
            def default_personality(self) -> Personality:
                return Personality()

            @property
            def default_goals(self) -> list[GoalConfig]:
                return []

            @property
            def default_capabilities(self) -> list[str]:
                return []

        config = _make_config()
        emp = MinimalEmployee(config)
        # Should not raise
        await emp.on_start()

    @pytest.mark.asyncio
    async def test_default_on_stop_is_noop(self):
        """Default on_stop() does nothing."""

        class MinimalEmployee(DigitalEmployee):
            @property
            def default_personality(self) -> Personality:
                return Personality()

            @property
            def default_goals(self) -> list[GoalConfig]:
                return []

            @property
            def default_capabilities(self) -> list[str]:
                return []

        config = _make_config()
        emp = MinimalEmployee(config)
        await emp.on_stop()
