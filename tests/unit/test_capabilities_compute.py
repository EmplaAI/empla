"""
Unit tests for ComputeCapability.

All tests use pytest's tmp_path fixture for real filesystem operations.
Script execution tests use the real Python interpreter via subprocess.
"""

import sys
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest

from empla.capabilities.base import (
    CAPABILITY_COMPUTE,
    Action,
)
from empla.capabilities.compute import (
    DEFAULT_BLOCKED_BUILTINS,
    DEFAULT_BLOCKED_MODULES,
    ComputeCapability,
    ComputeConfig,
    SubprocessResult,
    check_code_safety,
)

# -------------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------------


def make_capability(
    tmp_path: Path,
    *,
    tenant_id: UUID | None = None,
    employee_id: UUID | None = None,
    config_overrides: dict[str, Any] | None = None,
) -> tuple[ComputeCapability, dict[str, UUID]]:
    """Create a ComputeCapability pointed at tmp_path."""
    tid = tenant_id or uuid4()
    eid = employee_id or uuid4()
    cfg_kwargs: dict[str, Any] = {
        "workspace_base_path": str(tmp_path),
        "python_path": sys.executable,
    }
    if config_overrides:
        cfg_kwargs.update(config_overrides)
    config = ComputeConfig(**cfg_kwargs)
    cap = ComputeCapability(tid, eid, config)
    return cap, {"tenant_id": tid, "employee_id": eid}


def workspace_root(tmp_path: Path, tenant_id: UUID, employee_id: UUID) -> Path:
    return tmp_path / str(tenant_id) / str(employee_id)


# =========================================================================
# Config tests
# =========================================================================


class TestComputeConfig:
    def test_defaults(self):
        cfg = ComputeConfig()
        assert cfg.workspace_base_path == "workspaces"
        assert cfg.max_execution_seconds == 300
        assert cfg.max_output_bytes == 100_000
        assert cfg.python_path == sys.executable
        assert cfg.blocked_modules == DEFAULT_BLOCKED_MODULES
        assert cfg.blocked_builtins == DEFAULT_BLOCKED_BUILTINS
        assert cfg.allowed_packages_to_install is None
        assert cfg.log_pii is False

    def test_custom_values(self):
        cfg = ComputeConfig(
            workspace_base_path="/custom",
            max_execution_seconds=60,
            max_output_bytes=1000,
            python_path="/usr/bin/python3",
            blocked_modules=["os"],
            blocked_builtins=["eval"],
            allowed_packages_to_install=["pandas"],
        )
        assert cfg.workspace_base_path == "/custom"
        assert cfg.max_execution_seconds == 60
        assert cfg.max_output_bytes == 1000
        assert cfg.python_path == "/usr/bin/python3"
        assert cfg.blocked_modules == ["os"]
        assert cfg.blocked_builtins == ["eval"]
        assert cfg.allowed_packages_to_install == ["pandas"]

    def test_inherits_capability_config(self):
        cfg = ComputeConfig(enabled=False, rate_limit=10)
        assert cfg.enabled is False
        assert cfg.rate_limit == 10

    def test_empty_blocked_modules_rejected(self):
        with pytest.raises(ValueError, match="cannot be empty"):
            ComputeConfig(blocked_modules=[])

    def test_empty_blocked_builtins_rejected(self):
        with pytest.raises(ValueError, match="cannot be empty"):
            ComputeConfig(blocked_builtins=[])

    def test_empty_workspace_base_path_rejected(self):
        with pytest.raises(ValueError, match="cannot be empty"):
            ComputeConfig(workspace_base_path="")

    def test_whitespace_workspace_base_path_rejected(self):
        with pytest.raises(ValueError, match="cannot be empty"):
            ComputeConfig(workspace_base_path="   ")


# =========================================================================
# Code safety tests
# =========================================================================


class TestCodeSafety:
    def test_safe_code(self):
        code = "import json\nprint(json.dumps({'hello': 'world'}))"
        result = check_code_safety(code, DEFAULT_BLOCKED_MODULES, DEFAULT_BLOCKED_BUILTINS)
        assert result is None

    def test_blocked_import(self):
        code = "import subprocess"
        result = check_code_safety(code, DEFAULT_BLOCKED_MODULES, DEFAULT_BLOCKED_BUILTINS)
        assert result is not None
        assert "subprocess" in result

    def test_blocked_from_import(self):
        code = "from subprocess import run"
        result = check_code_safety(code, DEFAULT_BLOCKED_MODULES, DEFAULT_BLOCKED_BUILTINS)
        assert result is not None
        assert "subprocess" in result

    def test_blocked_submodule(self):
        code = "import http.server"
        result = check_code_safety(code, DEFAULT_BLOCKED_MODULES, DEFAULT_BLOCKED_BUILTINS)
        assert result is not None
        assert "http.server" in result

    def test_blocked_submodule_of_blocked(self):
        code = "import subprocess.popen"
        result = check_code_safety(code, DEFAULT_BLOCKED_MODULES, DEFAULT_BLOCKED_BUILTINS)
        assert result is not None
        assert "subprocess" in result

    def test_blocked_builtin_eval(self):
        code = "x = eval('1+1')"
        result = check_code_safety(code, DEFAULT_BLOCKED_MODULES, DEFAULT_BLOCKED_BUILTINS)
        assert result is not None
        assert "eval" in result

    def test_blocked_builtin_exec(self):
        code = "exec('print(1)')"
        result = check_code_safety(code, DEFAULT_BLOCKED_MODULES, DEFAULT_BLOCKED_BUILTINS)
        assert result is not None
        assert "exec" in result

    def test_blocked_builtin_compile(self):
        code = "compile('1+1', '<string>', 'eval')"
        result = check_code_safety(code, DEFAULT_BLOCKED_MODULES, DEFAULT_BLOCKED_BUILTINS)
        assert result is not None
        assert "compile" in result

    def test_blocked_builtin_import(self):
        code = "__import__('os')"
        result = check_code_safety(code, DEFAULT_BLOCKED_MODULES, DEFAULT_BLOCKED_BUILTINS)
        assert result is not None
        assert "__import__" in result

    def test_syntax_error(self):
        code = "def broken(:"
        result = check_code_safety(code, DEFAULT_BLOCKED_MODULES, DEFAULT_BLOCKED_BUILTINS)
        assert result is not None
        assert "Syntax error" in result

    def test_allowed_module_not_blocked(self):
        code = "import json\nimport math\nimport datetime"
        result = check_code_safety(code, DEFAULT_BLOCKED_MODULES, DEFAULT_BLOCKED_BUILTINS)
        assert result is None

    def test_blocked_import_os(self):
        code = "import os"
        result = check_code_safety(code, DEFAULT_BLOCKED_MODULES, DEFAULT_BLOCKED_BUILTINS)
        assert result is not None
        assert "os" in result

    def test_blocked_import_sys(self):
        code = "import sys"
        result = check_code_safety(code, DEFAULT_BLOCKED_MODULES, DEFAULT_BLOCKED_BUILTINS)
        assert result is not None
        assert "sys" in result

    def test_blocked_builtin_getattr(self):
        code = "x = getattr(obj, 'attr')"
        result = check_code_safety(code, DEFAULT_BLOCKED_MODULES, DEFAULT_BLOCKED_BUILTINS)
        assert result is not None
        assert "getattr" in result

    def test_blocked_builtin_globals(self):
        code = "x = globals()"
        result = check_code_safety(code, DEFAULT_BLOCKED_MODULES, DEFAULT_BLOCKED_BUILTINS)
        assert result is not None
        assert "globals" in result

    def test_empty_code(self):
        result = check_code_safety("", DEFAULT_BLOCKED_MODULES, DEFAULT_BLOCKED_BUILTINS)
        assert result is None

    def test_custom_blocked_modules(self):
        code = "import os"
        result = check_code_safety(code, ["os"], [])
        assert result is not None
        assert "os" in result


# =========================================================================
# Initialization tests
# =========================================================================


class TestComputeInit:
    @pytest.mark.asyncio
    async def test_workspace_created(self, tmp_path):
        cap, ids = make_capability(tmp_path)
        await cap.initialize()
        root = workspace_root(tmp_path, ids["tenant_id"], ids["employee_id"])
        assert root.is_dir()

    @pytest.mark.asyncio
    async def test_state_compute_dir_created(self, tmp_path):
        cap, ids = make_capability(tmp_path)
        await cap.initialize()
        root = workspace_root(tmp_path, ids["tenant_id"], ids["employee_id"])
        assert (root / ".state" / "compute").is_dir()

    @pytest.mark.asyncio
    async def test_capability_type(self, tmp_path):
        cap, _ = make_capability(tmp_path)
        assert cap.capability_type == CAPABILITY_COMPUTE

    @pytest.mark.asyncio
    async def test_initialized_flag(self, tmp_path):
        cap, _ = make_capability(tmp_path)
        assert cap._initialized is False
        await cap.initialize()
        assert cap._initialized is True

    @pytest.mark.asyncio
    async def test_is_healthy(self, tmp_path):
        cap, _ = make_capability(tmp_path)
        assert cap.is_healthy() is False
        await cap.initialize()
        assert cap.is_healthy() is True

    @pytest.mark.asyncio
    async def test_repr(self, tmp_path):
        cap, ids = make_capability(tmp_path)
        r = repr(cap)
        assert "ComputeCapability" in r
        assert "compute" in r
        assert str(ids["employee_id"]) in r


# =========================================================================
# execute_script tests
# =========================================================================


class TestExecuteScript:
    @pytest.mark.asyncio
    async def test_simple_script(self, tmp_path):
        cap, _ = make_capability(tmp_path)
        await cap.initialize()

        action = Action(
            capability="compute",
            operation="execute_script",
            parameters={"code": "print('hello world')"},
        )
        result = await cap._execute_action_impl(action)
        assert result.success is True
        assert "hello world" in result.output["stdout"]
        assert result.output["exit_code"] == 0

    @pytest.mark.asyncio
    async def test_script_with_error(self, tmp_path):
        cap, _ = make_capability(tmp_path)
        await cap.initialize()

        action = Action(
            capability="compute",
            operation="execute_script",
            parameters={"code": "raise ValueError('boom')"},
        )
        result = await cap._execute_action_impl(action)
        assert result.success is False
        assert result.output["exit_code"] != 0
        assert "boom" in result.output["stderr"]

    @pytest.mark.asyncio
    async def test_script_timeout(self, tmp_path):
        cap, _ = make_capability(tmp_path)
        await cap.initialize()

        action = Action(
            capability="compute",
            operation="execute_script",
            parameters={
                "code": "import time; time.sleep(10)",
                "timeout_seconds": 1,
            },
        )
        result = await cap._execute_action_impl(action)
        assert result.success is False
        assert "timed out" in result.output["stderr"].lower()
        assert result.output["exit_code"] == -1

    @pytest.mark.asyncio
    async def test_blocked_import_rejected(self, tmp_path):
        cap, _ = make_capability(tmp_path)
        await cap.initialize()

        action = Action(
            capability="compute",
            operation="execute_script",
            parameters={"code": "import subprocess"},
        )
        result = await cap._execute_action_impl(action)
        assert result.success is False
        assert "Blocked import" in result.error

    @pytest.mark.asyncio
    async def test_output_truncation(self, tmp_path):
        cap, _ = make_capability(tmp_path, config_overrides={"max_output_bytes": 50})
        await cap.initialize()

        action = Action(
            capability="compute",
            operation="execute_script",
            parameters={"code": "print('x' * 200)"},
        )
        result = await cap._execute_action_impl(action)
        assert result.success is True
        assert "truncated" in result.output["stdout"]

    @pytest.mark.asyncio
    async def test_cwd_is_workspace(self, tmp_path):
        cap, ids = make_capability(tmp_path)
        await cap.initialize()

        action = Action(
            capability="compute",
            operation="execute_script",
            parameters={"code": "from pathlib import Path; print(Path.cwd())"},
        )
        result = await cap._execute_action_impl(action)
        assert result.success is True
        root = workspace_root(tmp_path, ids["tenant_id"], ids["employee_id"])
        assert str(root.resolve()) in result.output["stdout"]

    @pytest.mark.asyncio
    async def test_read_workspace_files(self, tmp_path):
        cap, ids = make_capability(tmp_path)
        await cap.initialize()
        root = workspace_root(tmp_path, ids["tenant_id"], ids["employee_id"])
        (root / "data.txt").write_text("test_data_123")

        action = Action(
            capability="compute",
            operation="execute_script",
            parameters={
                "code": "print(open('data.txt').read())",
            },
        )
        result = await cap._execute_action_impl(action)
        assert result.success is True
        assert "test_data_123" in result.output["stdout"]

    @pytest.mark.asyncio
    async def test_write_workspace_files(self, tmp_path):
        cap, ids = make_capability(tmp_path)
        await cap.initialize()
        root = workspace_root(tmp_path, ids["tenant_id"], ids["employee_id"])

        action = Action(
            capability="compute",
            operation="execute_script",
            parameters={
                "code": "open('output.txt', 'w').write('result_456')",
            },
        )
        result = await cap._execute_action_impl(action)
        assert result.success is True
        assert (root / "output.txt").read_text() == "result_456"

    @pytest.mark.asyncio
    async def test_temp_file_cleaned_up(self, tmp_path):
        cap, ids = make_capability(tmp_path)
        await cap.initialize()
        root = workspace_root(tmp_path, ids["tenant_id"], ids["employee_id"])
        temp_dir = root / ".state" / "compute"

        action = Action(
            capability="compute",
            operation="execute_script",
            parameters={"code": "print('clean')"},
        )
        await cap._execute_action_impl(action)

        # Temp script should be cleaned up after execution
        py_files = list(temp_dir.glob("script_*.py"))
        assert len(py_files) == 0

    @pytest.mark.asyncio
    async def test_metadata_includes_duration(self, tmp_path):
        cap, _ = make_capability(tmp_path)
        await cap.initialize()

        action = Action(
            capability="compute",
            operation="execute_script",
            parameters={"code": "print(1)"},
        )
        result = await cap._execute_action_impl(action)
        assert "duration_ms" in result.metadata
        assert result.metadata["duration_ms"] > 0


# =========================================================================
# execute_file tests
# =========================================================================


class TestExecuteFile:
    @pytest.mark.asyncio
    async def test_execute_file_success(self, tmp_path):
        cap, ids = make_capability(tmp_path)
        await cap.initialize()
        root = workspace_root(tmp_path, ids["tenant_id"], ids["employee_id"])
        (root / "scripts").mkdir(parents=True, exist_ok=True)
        (root / "scripts" / "hello.py").write_text("print('from file')")

        action = Action(
            capability="compute",
            operation="execute_file",
            parameters={"script_path": "scripts/hello.py"},
        )
        result = await cap._execute_action_impl(action)
        assert result.success is True
        assert "from file" in result.output["stdout"]

    @pytest.mark.asyncio
    async def test_file_not_found(self, tmp_path):
        cap, _ = make_capability(tmp_path)
        await cap.initialize()

        action = Action(
            capability="compute",
            operation="execute_file",
            parameters={"script_path": "nonexistent.py"},
        )
        result = await cap._execute_action_impl(action)
        assert result.success is False
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_non_py_rejected(self, tmp_path):
        cap, ids = make_capability(tmp_path)
        await cap.initialize()
        root = workspace_root(tmp_path, ids["tenant_id"], ids["employee_id"])
        (root / "script.sh").write_text("echo hello")

        action = Action(
            capability="compute",
            operation="execute_file",
            parameters={"script_path": "script.sh"},
        )
        result = await cap._execute_action_impl(action)
        assert result.success is False
        assert ".py" in result.error

    @pytest.mark.asyncio
    async def test_path_traversal_blocked(self, tmp_path):
        cap, _ = make_capability(tmp_path)
        await cap.initialize()

        action = Action(
            capability="compute",
            operation="execute_file",
            parameters={"script_path": "../../evil.py"},
        )
        result = await cap._execute_action_impl(action)
        assert result.success is False
        assert "traversal" in result.error.lower()

    @pytest.mark.asyncio
    async def test_with_args(self, tmp_path):
        cap, ids = make_capability(tmp_path)
        await cap.initialize()
        root = workspace_root(tmp_path, ids["tenant_id"], ids["employee_id"])
        # Use argparse to access argv without directly importing sys (which is blocked)
        (root / "echo_args.py").write_text(
            "import argparse\n"
            "p = argparse.ArgumentParser()\n"
            "p.add_argument('words', nargs='*')\n"
            "print(' '.join(p.parse_args().words))\n"
        )

        action = Action(
            capability="compute",
            operation="execute_file",
            parameters={"script_path": "echo_args.py", "args": ["hello", "world"]},
        )
        result = await cap._execute_action_impl(action)
        assert result.success is True
        assert "hello world" in result.output["stdout"]

    @pytest.mark.asyncio
    async def test_blocked_content_in_file(self, tmp_path):
        cap, ids = make_capability(tmp_path)
        await cap.initialize()
        root = workspace_root(tmp_path, ids["tenant_id"], ids["employee_id"])
        (root / "evil.py").write_text("import subprocess\nsubprocess.run(['ls'])")

        action = Action(
            capability="compute",
            operation="execute_file",
            parameters={"script_path": "evil.py"},
        )
        result = await cap._execute_action_impl(action)
        assert result.success is False
        assert "Blocked import" in result.error

    @pytest.mark.asyncio
    async def test_absolute_path_blocked(self, tmp_path):
        cap, _ = make_capability(tmp_path)
        await cap.initialize()

        action = Action(
            capability="compute",
            operation="execute_file",
            parameters={"script_path": "/etc/evil.py"},
        )
        result = await cap._execute_action_impl(action)
        assert result.success is False
        assert "Absolute" in result.error


# =========================================================================
# install_package tests
# =========================================================================


class TestInstallPackage:
    @pytest.mark.asyncio
    async def test_valid_package_mock(self, tmp_path):
        cap, _ = make_capability(tmp_path)
        await cap.initialize()

        with patch.object(cap, "_run_subprocess", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = SubprocessResult(
                "Successfully installed testpkg", "", 0, 1000.0
            )

            action = Action(
                capability="compute",
                operation="install_package",
                parameters={"package": "testpkg"},
            )
            result = await cap._execute_action_impl(action)
            assert result.success is True
            assert result.output["package"] == "testpkg"
            mock_run.assert_called_once()

    @pytest.mark.asyncio
    async def test_invalid_package_name(self, tmp_path):
        cap, _ = make_capability(tmp_path)
        await cap.initialize()

        action = Action(
            capability="compute",
            operation="install_package",
            parameters={"package": "../../evil"},
        )
        result = await cap._execute_action_impl(action)
        assert result.success is False
        assert "Invalid package name" in result.error

    @pytest.mark.asyncio
    async def test_invalid_package_name_spaces(self, tmp_path):
        cap, _ = make_capability(tmp_path)
        await cap.initialize()

        action = Action(
            capability="compute",
            operation="install_package",
            parameters={"package": "my package"},
        )
        result = await cap._execute_action_impl(action)
        assert result.success is False
        assert "Invalid package name" in result.error

    @pytest.mark.asyncio
    async def test_allowlist_blocks(self, tmp_path):
        cap, _ = make_capability(
            tmp_path, config_overrides={"allowed_packages_to_install": ["pandas"]}
        )
        await cap.initialize()

        action = Action(
            capability="compute",
            operation="install_package",
            parameters={"package": "numpy"},
        )
        result = await cap._execute_action_impl(action)
        assert result.success is False
        assert "not in the allowed list" in result.error

    @pytest.mark.asyncio
    async def test_allowlist_allows(self, tmp_path):
        cap, _ = make_capability(
            tmp_path, config_overrides={"allowed_packages_to_install": ["pandas"]}
        )
        await cap.initialize()

        with patch.object(cap, "_run_subprocess", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = SubprocessResult("Installed", "", 0, 500.0)

            action = Action(
                capability="compute",
                operation="install_package",
                parameters={"package": "pandas"},
            )
            result = await cap._execute_action_impl(action)
            assert result.success is True

    @pytest.mark.asyncio
    async def test_with_version(self, tmp_path):
        cap, _ = make_capability(tmp_path)
        await cap.initialize()

        with patch.object(cap, "_run_subprocess", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = SubprocessResult("Installed", "", 0, 500.0)

            action = Action(
                capability="compute",
                operation="install_package",
                parameters={"package": "pandas", "version": "2.0.0"},
            )
            result = await cap._execute_action_impl(action)
            assert result.success is True
            assert result.output["package"] == "pandas==2.0.0"

            # Verify the subprocess was called with the versioned package
            call_args = mock_run.call_args
            cmd = call_args[0][0]
            assert "pandas==2.0.0" in cmd

    @pytest.mark.asyncio
    async def test_allowlist_pep503_normalized(self, tmp_path):
        """Allowlist comparison should be case-insensitive and normalize separators per PEP 503."""
        cap, _ = make_capability(
            tmp_path, config_overrides={"allowed_packages_to_install": ["Scikit-Learn"]}
        )
        await cap.initialize()

        with patch.object(cap, "_run_subprocess", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = SubprocessResult("Installed", "", 0, 500.0)

            # "scikit_learn" should match "Scikit-Learn" after PEP 503 normalization
            action = Action(
                capability="compute",
                operation="install_package",
                parameters={"package": "scikit_learn"},
            )
            result = await cap._execute_action_impl(action)
            assert result.success is True


# =========================================================================
# Parameter validation tests
# =========================================================================


class TestParameterValidation:
    @pytest.mark.asyncio
    async def test_missing_code(self, tmp_path):
        cap, _ = make_capability(tmp_path)
        await cap.initialize()

        action = Action(capability="compute", operation="execute_script", parameters={})
        result = await cap._execute_action_impl(action)
        assert result.success is False
        assert "missing required parameters" in result.error.lower()
        assert "code" in result.error

    @pytest.mark.asyncio
    async def test_missing_script_path(self, tmp_path):
        cap, _ = make_capability(tmp_path)
        await cap.initialize()

        action = Action(capability="compute", operation="execute_file", parameters={})
        result = await cap._execute_action_impl(action)
        assert result.success is False
        assert "script_path" in result.error

    @pytest.mark.asyncio
    async def test_missing_package(self, tmp_path):
        cap, _ = make_capability(tmp_path)
        await cap.initialize()

        action = Action(capability="compute", operation="install_package", parameters={})
        result = await cap._execute_action_impl(action)
        assert result.success is False
        assert "package" in result.error

    @pytest.mark.asyncio
    async def test_unknown_operation(self, tmp_path):
        cap, _ = make_capability(tmp_path)
        await cap.initialize()

        action = Action(capability="compute", operation="launch_rockets", parameters={})
        result = await cap._execute_action_impl(action)
        assert result.success is False
        assert "Unknown operation" in result.error

    @pytest.mark.asyncio
    async def test_timeout_seconds_invalid_type(self, tmp_path):
        cap, _ = make_capability(tmp_path)
        await cap.initialize()

        action = Action(
            capability="compute",
            operation="execute_script",
            parameters={"code": "print(1)", "timeout_seconds": "not-a-number"},
        )
        result = await cap._execute_action_impl(action)
        assert result.success is False
        assert "timeout_seconds" in result.error

    @pytest.mark.asyncio
    async def test_timeout_seconds_numeric_string_accepted(self, tmp_path):
        cap, _ = make_capability(tmp_path)
        await cap.initialize()

        action = Action(
            capability="compute",
            operation="execute_script",
            parameters={"code": "print(1)", "timeout_seconds": "5"},
        )
        result = await cap._execute_action_impl(action)
        assert result.success is True

    @pytest.mark.asyncio
    async def test_timeout_seconds_negative_rejected(self, tmp_path):
        cap, _ = make_capability(tmp_path)
        await cap.initialize()

        action = Action(
            capability="compute",
            operation="execute_script",
            parameters={"code": "print(1)", "timeout_seconds": -1},
        )
        result = await cap._execute_action_impl(action)
        assert result.success is False
        assert "positive" in result.error.lower()

    @pytest.mark.asyncio
    async def test_timeout_seconds_zero_rejected(self, tmp_path):
        cap, _ = make_capability(tmp_path)
        await cap.initialize()

        action = Action(
            capability="compute",
            operation="execute_script",
            parameters={"code": "print(1)", "timeout_seconds": 0},
        )
        result = await cap._execute_action_impl(action)
        assert result.success is False
        assert "positive" in result.error.lower()

    @pytest.mark.asyncio
    async def test_args_invalid_type(self, tmp_path):
        cap, ids = make_capability(tmp_path)
        await cap.initialize()
        root = workspace_root(tmp_path, ids["tenant_id"], ids["employee_id"])
        (root / "test.py").write_text("print('ok')")

        action = Action(
            capability="compute",
            operation="execute_file",
            parameters={"script_path": "test.py", "args": "not-a-list"},
        )
        result = await cap._execute_action_impl(action)
        assert result.success is False
        assert "args must be a list" in result.error

    @pytest.mark.asyncio
    async def test_code_must_be_string(self, tmp_path):
        cap, _ = make_capability(tmp_path)
        await cap.initialize()

        action = Action(
            capability="compute",
            operation="execute_script",
            parameters={"code": 123},
        )
        result = await cap._execute_action_impl(action)
        assert result.success is False
        assert "'code' must be a string" in result.error

    @pytest.mark.asyncio
    async def test_script_path_must_be_string(self, tmp_path):
        cap, _ = make_capability(tmp_path)
        await cap.initialize()

        action = Action(
            capability="compute",
            operation="execute_file",
            parameters={"script_path": ["not", "a", "string"]},
        )
        result = await cap._execute_action_impl(action)
        assert result.success is False
        assert "'script_path' must be a string" in result.error

    @pytest.mark.asyncio
    async def test_package_must_be_string(self, tmp_path):
        cap, _ = make_capability(tmp_path)
        await cap.initialize()

        action = Action(
            capability="compute",
            operation="install_package",
            parameters={"package": ["numpy"]},
        )
        result = await cap._execute_action_impl(action)
        assert result.success is False
        assert "'package' must be a string" in result.error

    @pytest.mark.asyncio
    async def test_version_must_be_string(self, tmp_path):
        cap, _ = make_capability(tmp_path)
        await cap.initialize()

        action = Action(
            capability="compute",
            operation="install_package",
            parameters={"package": "numpy", "version": 2},
        )
        result = await cap._execute_action_impl(action)
        assert result.success is False
        assert "'version' must be a string" in result.error

    @pytest.mark.asyncio
    async def test_subprocess_startup_failure(self, tmp_path):
        """RuntimeError from _run_subprocess returns ActionResult, not exception."""
        cap, _ = make_capability(tmp_path, config_overrides={"python_path": "/nonexistent/python"})
        await cap.initialize()

        action = Action(
            capability="compute",
            operation="execute_script",
            parameters={"code": "print(1)"},
        )
        result = await cap._execute_action_impl(action)
        assert result.success is False
        assert "not found" in result.error.lower() or "Failed" in result.error


# =========================================================================
# Perception tests
# =========================================================================


class TestPerception:
    @pytest.mark.asyncio
    async def test_perceive_returns_empty(self, tmp_path):
        cap, _ = make_capability(tmp_path)
        await cap.initialize()
        observations = await cap.perceive()
        assert observations == []

    @pytest.mark.asyncio
    async def test_perceive_before_init(self, tmp_path):
        cap, _ = make_capability(tmp_path)
        # perceive() should not raise before initialization
        observations = await cap.perceive()
        assert observations == []


# =========================================================================
# Shutdown tests
# =========================================================================


class TestShutdown:
    @pytest.mark.asyncio
    async def test_shutdown_cleans_temp_files(self, tmp_path):
        cap, ids = make_capability(tmp_path)
        await cap.initialize()
        root = workspace_root(tmp_path, ids["tenant_id"], ids["employee_id"])
        temp_dir = root / ".state" / "compute"

        # Place a temp file
        (temp_dir / "script_abc123.py").write_text("print('leftover')")

        await cap.shutdown()
        assert len(list(temp_dir.glob("*.py"))) == 0

    @pytest.mark.asyncio
    async def test_shutdown_before_init(self, tmp_path):
        cap, _ = make_capability(tmp_path)
        # Should not raise
        await cap.shutdown()


# =========================================================================
# PII redaction tests
# =========================================================================


class TestRedaction:
    def test_redact_code(self, tmp_path):
        cap, _ = make_capability(tmp_path)
        result = cap._redact_code("print('secret data')")
        assert result.startswith("[code:")
        assert len(result) == len("[code:") + 8 + 1  # 8 hex chars + ]

    def test_redact_code_deterministic(self, tmp_path):
        cap, _ = make_capability(tmp_path)
        r1 = cap._redact_code("same code")
        r2 = cap._redact_code("same code")
        assert r1 == r2

    def test_redact_code_different_for_different_input(self, tmp_path):
        cap, _ = make_capability(tmp_path)
        r1 = cap._redact_code("code A")
        r2 = cap._redact_code("code B")
        assert r1 != r2


# =========================================================================
# _run_subprocess helper tests
# =========================================================================


class TestRunSubprocess:
    @pytest.mark.asyncio
    async def test_returns_stdout_stderr_exitcode(self, tmp_path):
        cap, _ = make_capability(tmp_path)
        await cap.initialize()

        stdout, stderr, exit_code, duration_ms = await cap._run_subprocess(
            [sys.executable, "-c", "import sys; print('out'); print('err', file=sys.stderr)"],
            wall_clock_timeout=10,
            cwd=str(tmp_path),
        )
        assert "out" in stdout
        assert "err" in stderr
        assert exit_code == 0
        assert duration_ms > 0

    @pytest.mark.asyncio
    async def test_timeout_kills_process(self, tmp_path):
        cap, _ = make_capability(tmp_path)
        await cap.initialize()

        result = await cap._run_subprocess(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            wall_clock_timeout=1,
            cwd=str(tmp_path),
        )
        assert result.exit_code == -1
        assert "timed out" in result.stderr.lower()


# =========================================================================
# Edge case tests
# =========================================================================


class TestEdgeCases:
    @pytest.mark.asyncio
    async def test_require_initialized_raises(self, tmp_path):
        cap, _ = make_capability(tmp_path)
        with pytest.raises(RuntimeError, match="must be initialized"):
            cap._require_initialized()

    @pytest.mark.asyncio
    async def test_resolve_safe_path_empty(self, tmp_path):
        cap, _ = make_capability(tmp_path)
        await cap.initialize()
        with pytest.raises(ValueError, match="empty"):
            cap._resolve_safe_path("")

    @pytest.mark.asyncio
    async def test_resolve_safe_path_absolute(self, tmp_path):
        cap, _ = make_capability(tmp_path)
        await cap.initialize()
        with pytest.raises(ValueError, match="Absolute"):
            cap._resolve_safe_path("/etc/passwd")

    @pytest.mark.asyncio
    async def test_resolve_safe_path_traversal(self, tmp_path):
        cap, _ = make_capability(tmp_path)
        await cap.initialize()
        with pytest.raises(ValueError, match="traversal"):
            cap._resolve_safe_path("../../../escape")

    @pytest.mark.asyncio
    async def test_script_with_multiline_output(self, tmp_path):
        cap, _ = make_capability(tmp_path)
        await cap.initialize()

        code = "for i in range(5): print(f'line {i}')"
        action = Action(
            capability="compute",
            operation="execute_script",
            parameters={"code": code},
        )
        result = await cap._execute_action_impl(action)
        assert result.success is True
        assert "line 0" in result.output["stdout"]
        assert "line 4" in result.output["stdout"]

    @pytest.mark.asyncio
    async def test_resolve_safe_path_state_dir_blocked(self, tmp_path):
        cap, _ = make_capability(tmp_path)
        await cap.initialize()
        with pytest.raises(ValueError, match=r"\.state/"):
            cap._resolve_safe_path(".state/compute/evil.py")

    @pytest.mark.asyncio
    async def test_is_inside_state_dir(self, tmp_path):
        cap, ids = make_capability(tmp_path)
        await cap.initialize()
        root = workspace_root(tmp_path, ids["tenant_id"], ids["employee_id"]).resolve()
        assert cap._is_inside_state_dir(root / ".state" / "compute" / "test.py")
        assert cap._is_inside_state_dir(root / ".state" / "test.py")
        assert not cap._is_inside_state_dir(root / "test.py")
        assert not cap._is_inside_state_dir(root / "scripts" / "test.py")

    @pytest.mark.asyncio
    async def test_install_package_invalid_version(self, tmp_path):
        cap, _ = make_capability(tmp_path)
        await cap.initialize()

        action = Action(
            capability="compute",
            operation="install_package",
            parameters={"package": "numpy", "version": "1.0; rm -rf /"},
        )
        result = await cap._execute_action_impl(action)
        assert result.success is False
        assert "Invalid version" in result.error

    @pytest.mark.asyncio
    async def test_execute_file_unreadable(self, tmp_path):
        """Test execute_file with a file that can't be decoded as UTF-8."""
        cap, ids = make_capability(tmp_path)
        await cap.initialize()
        root = workspace_root(tmp_path, ids["tenant_id"], ids["employee_id"])
        # Write binary content that is not valid UTF-8
        (root / "binary.py").write_bytes(b"\x80\x81\x82\x83")

        action = Action(
            capability="compute",
            operation="execute_file",
            parameters={"script_path": "binary.py"},
        )
        result = await cap._execute_action_impl(action)
        assert result.success is False
        assert "Cannot read" in result.error

    def test_subprocess_result_named_tuple(self):
        """SubprocessResult fields are accessible by name and index."""
        r = SubprocessResult(stdout="out", stderr="err", exit_code=0, duration_ms=100.0)
        assert r.stdout == "out"
        assert r.stderr == "err"
        assert r.exit_code == 0
        assert r.duration_ms == 100.0
        # Also works as tuple
        out, _err, code, _dur = r
        assert out == "out"
        assert code == 0

    @pytest.mark.asyncio
    async def test_max_output_bytes_zero(self, tmp_path):
        """max_output_bytes=0 should truncate all output."""
        cap, _ = make_capability(tmp_path, config_overrides={"max_output_bytes": 0})
        await cap.initialize()

        action = Action(
            capability="compute",
            operation="execute_script",
            parameters={"code": "print('hello')"},
        )
        result = await cap._execute_action_impl(action)
        assert result.success is True
        assert "truncated" in result.output["stdout"]

    @pytest.mark.asyncio
    async def test_symlink_escape_blocked(self, tmp_path):
        """A symlink pointing outside the workspace should be caught."""
        cap, ids = make_capability(tmp_path)
        await cap.initialize()
        root = workspace_root(tmp_path, ids["tenant_id"], ids["employee_id"])

        # Create a symlink that points outside the workspace
        escape_target = tmp_path / "outside.py"
        escape_target.write_text("print('escaped')")
        symlink = root / "link.py"
        symlink.symlink_to(escape_target)

        action = Action(
            capability="compute",
            operation="execute_file",
            parameters={"script_path": "link.py"},
        )
        result = await cap._execute_action_impl(action)
        assert result.success is False
        assert "escapes" in result.error.lower()
