"""
Compute Capability

Gives digital employees sandboxed Python execution — data analysis, chart
generation, report building. Combined with WorkspaceCapability this forms the
Digital Desk that makes employees productive.

Approach: subprocess in the same process. No Docker, no separate service.
Extract later if scaling demands it.

Operations:
- execute_script: Run inline Python code in a subprocess
- execute_file: Run a .py file from the workspace
- install_package: pip install a package (with optional allowlist)
"""

import ast
import asyncio
import hashlib
import logging
import re
import sys
from pathlib import Path
from time import time
from typing import Any, NamedTuple
from uuid import UUID, uuid4

from pydantic import Field, field_validator

from empla.capabilities.base import (
    CAPABILITY_COMPUTE,
    Action,
    ActionResult,
    BaseCapability,
    CapabilityConfig,
    Observation,
)

logger = logging.getLogger(__name__)

# Default modules blocked from import in sandboxed scripts
DEFAULT_BLOCKED_MODULES: list[str] = [
    "os",
    "sys",
    "subprocess",
    "shutil",
    "socket",
    "http.server",
    "ctypes",
    "multiprocessing",
    "_thread",
    "signal",
    "importlib",
    "builtins",
    "code",
    "codeop",
    "compileall",
    "py_compile",
    "webbrowser",
    "antigravity",
    "pty",
    "pickle",
    "gc",
]

# Default builtins blocked in sandboxed scripts
DEFAULT_BLOCKED_BUILTINS: list[str] = [
    "exec",
    "eval",
    "compile",
    "__import__",
    "getattr",
    "globals",
    "locals",
    "vars",
]

# Required parameters for each compute operation
_REQUIRED_PARAMS: dict[str, list[str]] = {
    "execute_script": ["code"],
    "execute_file": ["script_path"],
    "install_package": ["package"],
}

# Regex for valid pip package names (PEP 508 simplified)
_PACKAGE_NAME_RE = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9._-]*[A-Za-z0-9])?$")

# PEP 503 normalization: lowercase and collapse runs of [-_.] to '-'
_PEP503_NORMALIZE_RE = re.compile(r"[-_.]+")


def _canonicalize_name(name: str) -> str:
    """Normalize a package name per PEP 503."""
    return _PEP503_NORMALIZE_RE.sub("-", name).lower()


# Regex for valid pip version specifiers
_VERSION_RE = re.compile(r"^[A-Za-z0-9._\-+*]+$")


class SubprocessResult(NamedTuple):
    """Result of a sandboxed subprocess execution."""

    stdout: str
    stderr: str
    exit_code: int
    duration_ms: float


def check_code_safety(
    code: str,
    blocked_modules: list[str],
    blocked_builtins: list[str],
) -> str | None:
    """Check Python code for unsafe imports and builtin calls via AST analysis.

    This is a best-effort defense layer, not a security boundary. Determined
    bypass is possible via metaclasses, attribute access on builtins objects,
    etc. Full sandboxing requires Docker (deferred).

    Args:
        code: Python source code to check.
        blocked_modules: Module names to block (including submodules).
        blocked_builtins: Builtin function names to block.

    Returns:
        None if the code is safe, or an error message string if blocked.
    """
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return f"Syntax error in code: {e}"

    for node in ast.walk(tree):
        # Check `import foo` / `import foo.bar`
        if isinstance(node, ast.Import):
            for alias in node.names:
                if _is_blocked_module(alias.name, blocked_modules):
                    return f"Blocked import: '{alias.name}'"

        # Check `from foo import bar` / `from foo.bar import baz`
        elif isinstance(node, ast.ImportFrom):
            if node.module and _is_blocked_module(node.module, blocked_modules):
                return f"Blocked import: '{node.module}'"

        # Check calls to blocked builtins: eval(...), exec(...), etc.
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in blocked_builtins
        ):
            return f"Blocked builtin call: '{node.func.id}'"

    return None


def _is_blocked_module(module_name: str, blocked_modules: list[str]) -> bool:
    """Check if a module name matches any blocked module (including submodules)."""
    for blocked in blocked_modules:
        if module_name == blocked or module_name.startswith(blocked + "."):
            return True
    return False


class ComputeConfig(CapabilityConfig):
    """Configuration for the compute capability.

    Note: The inherited ``timeout_seconds`` field from ``CapabilityConfig`` is
    not used by ``ComputeCapability``.  Use ``max_execution_seconds`` to
    control subprocess wall-clock timeout.
    """

    workspace_base_path: str = "workspaces"
    """Root directory for workspaces (same as WorkspaceConfig.base_path)"""

    max_execution_seconds: int = Field(default=300, ge=1)
    """Subprocess wall-clock timeout in seconds"""

    max_output_bytes: int = Field(default=100_000, ge=0)
    """Truncate stdout/stderr beyond this many bytes"""

    python_path: str = Field(default_factory=lambda: sys.executable)
    """Python interpreter path (defaults to current interpreter)"""

    blocked_modules: list[str] = Field(default_factory=lambda: list(DEFAULT_BLOCKED_MODULES))
    """Modules blocked from import in sandboxed scripts"""

    blocked_builtins: list[str] = Field(default_factory=lambda: list(DEFAULT_BLOCKED_BUILTINS))
    """Builtin functions blocked in sandboxed scripts"""

    allowed_packages_to_install: list[str] | None = None
    """Optional pip allowlist. None means all packages allowed."""

    log_pii: bool = False
    """If True, log code content; if False, log SHA256 hash only"""

    @field_validator("workspace_base_path")
    @classmethod
    def _validate_workspace_base_path(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("workspace_base_path cannot be empty")
        return v

    @field_validator("blocked_modules")
    @classmethod
    def _validate_blocked_modules(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError(
                "blocked_modules cannot be empty — this would disable all import safety checks"
            )
        return v

    @field_validator("blocked_builtins")
    @classmethod
    def _validate_blocked_builtins(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError(
                "blocked_builtins cannot be empty — this would disable all builtin safety checks"
            )
        return v


class ComputeCapability(BaseCapability):
    """
    Compute capability — sandboxed Python execution for digital employees.

    Each employee runs scripts in their workspace directory:
        workspace_base_path / tenant_id / employee_id /

    Security layers:
    - Pre-execution: AST scan blocks dangerous imports + builtins
    - Process: Timeout via asyncio.wait_for + SIGKILL
    - Output: Truncation to max_output_bytes
    - Filesystem: cwd=workspace; execute_file validates paths
    - Packages: Name regex + version regex + optional allowlist

    Accepted limitations (deferred to Docker): network access, absolute path
    access, resource limits beyond timeout, AST bypass via metaclasses or
    attribute access on builtins objects.
    """

    def __init__(
        self,
        tenant_id: UUID,
        employee_id: UUID,
        config: ComputeConfig,
    ) -> None:
        super().__init__(tenant_id, employee_id, config)
        self.config: ComputeConfig = config
        self._workspace_root: Path | None = None
        self._temp_dir: Path | None = None

    @property
    def capability_type(self) -> str:
        return CAPABILITY_COMPUTE

    def _require_initialized(self) -> tuple[Path, Path]:
        """Return (workspace_root, temp_dir) or raise if not initialized."""
        if self._workspace_root is None or self._temp_dir is None:
            raise RuntimeError("ComputeCapability must be initialized before use")
        return self._workspace_root, self._temp_dir

    async def initialize(self) -> None:
        """Resolve workspace root and create temp directory for scripts."""
        root = Path(self.config.workspace_base_path) / str(self.tenant_id) / str(self.employee_id)

        def _setup() -> None:
            root.mkdir(parents=True, exist_ok=True)
            (root / ".state" / "compute").mkdir(parents=True, exist_ok=True)

        await asyncio.to_thread(_setup)
        self._workspace_root = root.resolve()
        self._temp_dir = self._workspace_root / ".state" / "compute"
        self._initialized = True

        logger.info(
            "Compute capability initialized",
            extra={
                "employee_id": str(self.employee_id),
                "workspace_root": (
                    str(self._workspace_root)
                    if self.config.log_pii
                    else self._redact_code(str(self._workspace_root))
                ),
            },
        )

    def get_tool_schemas(self) -> list[dict[str, Any]]:
        """Return tool schemas for compute operations."""
        return [
            {
                "name": "compute.execute_script",
                "description": "Execute inline Python code in a sandboxed subprocess",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "code": {"type": "string", "description": "Python code to execute"},
                        "timeout_seconds": {
                            "type": "integer",
                            "description": "Execution timeout in seconds, must be positive (optional)",
                            "minimum": 1,
                        },
                    },
                    "required": ["code"],
                },
            },
            {
                "name": "compute.execute_file",
                "description": "Execute a .py file from the workspace",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "script_path": {
                            "type": "string",
                            "description": "Relative path to .py file in workspace",
                        },
                        "args": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Command-line arguments for the script",
                        },
                    },
                    "required": ["script_path"],
                },
            },
            {
                "name": "compute.install_package",
                "description": "Install a pip package for use in scripts",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "package": {"type": "string", "description": "Package name to install"},
                        "version": {
                            "type": "string",
                            "description": "Version constraint (optional)",
                        },
                    },
                    "required": ["package"],
                },
            },
        ]

    async def perceive(self) -> list[Observation]:
        """No background jobs in subprocess mode — always returns empty list."""
        return []

    async def _execute_action_impl(self, action: Action) -> ActionResult:
        operation = action.operation
        params = action.parameters

        required = _REQUIRED_PARAMS.get(operation)
        if required is None:
            return ActionResult(success=False, error=f"Unknown operation: {operation}")

        missing = [p for p in required if p not in params]
        if missing:
            return ActionResult(
                success=False,
                error=f"Operation '{operation}' missing required parameters: {missing}",
            )

        if operation == "execute_script":
            code = params["code"]
            if not isinstance(code, str):
                return ActionResult(
                    success=False,
                    error=f"'code' must be a string, got: {type(code).__name__}",
                )
            raw_timeout = params.get("timeout_seconds")
            if raw_timeout is not None:
                try:
                    raw_timeout = int(raw_timeout)
                except (TypeError, ValueError):
                    return ActionResult(
                        success=False,
                        error=f"timeout_seconds must be an integer, got: {type(raw_timeout).__name__}",
                    )
                if raw_timeout <= 0:
                    return ActionResult(
                        success=False,
                        error=f"timeout_seconds must be a positive integer, got: {raw_timeout}",
                    )
            return await self._execute_script(code, timeout_seconds=raw_timeout)

        if operation == "execute_file":
            script_path = params["script_path"]
            if not isinstance(script_path, str):
                return ActionResult(
                    success=False,
                    error=f"'script_path' must be a string, got: {type(script_path).__name__}",
                )
            raw_args = params.get("args")
            if raw_args is not None and not isinstance(raw_args, list):
                return ActionResult(
                    success=False,
                    error=f"args must be a list of strings, got: {type(raw_args).__name__}",
                )
            return await self._execute_file(
                script_path,
                args=[str(a) for a in raw_args] if raw_args else None,
            )

        if operation == "install_package":
            package = params["package"]
            if not isinstance(package, str):
                return ActionResult(
                    success=False,
                    error=f"'package' must be a string, got: {type(package).__name__}",
                )
            version = params.get("version")
            if version is not None and not isinstance(version, str):
                return ActionResult(
                    success=False,
                    error=f"'version' must be a string, got: {type(version).__name__}",
                )
            return await self._install_package(package, version=version)

        return ActionResult(
            success=False, error=f"Unknown operation: {operation}"
        )  # pragma: no cover

    # ------------------------------------------------------------------
    # Operations
    # ------------------------------------------------------------------

    async def _execute_script(
        self,
        code: str,
        timeout_seconds: int | None = None,
    ) -> ActionResult:
        """Execute inline Python code in a sandboxed subprocess."""
        ws_root, temp_dir = self._require_initialized()

        # AST safety check
        error = check_code_safety(code, self.config.blocked_modules, self.config.blocked_builtins)
        if error:
            return ActionResult(success=False, error=error)

        # Write to temp file (uuid suffix prevents collisions across concurrent runs)
        code_hash = hashlib.sha256(code.encode()).hexdigest()[:12]
        temp_file = temp_dir / f"script_{code_hash}_{uuid4().hex[:8]}.py"

        def _write_temp() -> None:
            temp_file.write_text(code, encoding="utf-8")

        try:
            await asyncio.to_thread(_write_temp)
        except OSError as e:
            return ActionResult(
                success=False,
                error=f"Failed to write temporary script file: {e}",
            )

        timeout = timeout_seconds or self.config.max_execution_seconds

        try:
            result = await self._run_subprocess(
                [self.config.python_path, str(temp_file)],
                wall_clock_timeout=timeout,
                cwd=str(ws_root),
            )
        except RuntimeError as e:
            return ActionResult(success=False, error=str(e))
        finally:

            def _cleanup() -> None:
                try:
                    temp_file.unlink(missing_ok=True)
                except OSError as e:
                    logger.warning(
                        "Failed to clean up temp script file",
                        extra={
                            "employee_id": str(self.employee_id),
                            "error": str(e),
                        },
                    )

            await asyncio.to_thread(_cleanup)

        logger.info(
            "Script executed",
            extra={
                "employee_id": str(self.employee_id),
                "code": code if self.config.log_pii else self._redact_code(code),
                "exit_code": result.exit_code,
                "duration_ms": result.duration_ms,
            },
        )

        return ActionResult(
            success=result.exit_code == 0,
            output={
                "stdout": result.stdout,
                "stderr": result.stderr,
                "exit_code": result.exit_code,
            },
            error=result.stderr if result.exit_code != 0 else None,
            metadata={"duration_ms": result.duration_ms},
        )

    async def _execute_file(
        self,
        script_path: str,
        args: list[str] | None = None,
    ) -> ActionResult:
        """Execute a .py file from the workspace."""
        ws_root, _temp_dir = self._require_initialized()

        # Path validation
        try:
            full_path = self._resolve_safe_path(script_path)
        except ValueError as e:
            return ActionResult(success=False, error=str(e))

        if full_path.suffix != ".py":
            return ActionResult(
                success=False,
                error=f"Only .py files can be executed, got: '{full_path.suffix}'",
            )

        if not full_path.exists() or not full_path.is_file():
            return ActionResult(
                success=False,
                error=f"Script not found: {script_path}",
            )

        # Read and safety-check the file content
        def _read_file() -> str:
            return full_path.read_text(encoding="utf-8")

        try:
            code = await asyncio.to_thread(_read_file)
        except (UnicodeDecodeError, OSError) as e:
            return ActionResult(success=False, error=f"Cannot read script: {e}")

        error = check_code_safety(code, self.config.blocked_modules, self.config.blocked_builtins)
        if error:
            return ActionResult(success=False, error=error)

        # Execute the already-scanned code via a temp file to close the
        # TOCTOU gap (file could be modified between read and exec).
        # Use full_path as the temp name prefix so tracebacks show the
        # original filename.
        _ws_root, temp_dir = self._require_initialized()
        code_hash = hashlib.sha256(code.encode()).hexdigest()[:12]
        temp_file = temp_dir / f"file_{code_hash}_{uuid4().hex[:8]}.py"

        def _write_temp() -> None:
            temp_file.write_text(code, encoding="utf-8")

        try:
            await asyncio.to_thread(_write_temp)
        except OSError as e:
            return ActionResult(
                success=False,
                error=f"Failed to write temporary script file: {e}",
            )

        cmd = [self.config.python_path, str(temp_file)]
        if args:
            cmd.extend(args)

        try:
            result = await self._run_subprocess(
                cmd,
                wall_clock_timeout=self.config.max_execution_seconds,
                cwd=str(ws_root),
            )
        except RuntimeError as e:
            return ActionResult(success=False, error=str(e))
        finally:

            def _cleanup() -> None:
                try:
                    temp_file.unlink(missing_ok=True)
                except OSError as e:
                    logger.warning(
                        "Failed to clean up temp script file",
                        extra={
                            "employee_id": str(self.employee_id),
                            "error": str(e),
                        },
                    )

            await asyncio.to_thread(_cleanup)

        logger.info(
            "File executed",
            extra={
                "employee_id": str(self.employee_id),
                "script_path": (
                    script_path if self.config.log_pii else self._redact_code(script_path)
                ),
                "exit_code": result.exit_code,
                "duration_ms": result.duration_ms,
            },
        )

        return ActionResult(
            success=result.exit_code == 0,
            output={
                "stdout": result.stdout,
                "stderr": result.stderr,
                "exit_code": result.exit_code,
            },
            error=result.stderr if result.exit_code != 0 else None,
            metadata={"duration_ms": result.duration_ms},
        )

    async def _install_package(
        self,
        package: str,
        version: str | None = None,
    ) -> ActionResult:
        """Install a pip package with optional version constraint."""
        # Validate package name
        if not _PACKAGE_NAME_RE.match(package):
            return ActionResult(
                success=False,
                error=f"Invalid package name: '{package}'",
            )

        # Validate version string
        if version and not _VERSION_RE.match(version):
            return ActionResult(
                success=False,
                error=f"Invalid version specifier: '{version}'",
            )

        # Check allowlist (PEP 503 normalized comparison)
        if self.config.allowed_packages_to_install is not None:
            allowed_normalized = {
                _canonicalize_name(p) for p in self.config.allowed_packages_to_install
            }
            if _canonicalize_name(package) not in allowed_normalized:
                return ActionResult(
                    success=False,
                    error=(
                        f"Package '{package}' is not in the allowed list. "
                        f"Allowed: {self.config.allowed_packages_to_install}"
                    ),
                )

        pkg_spec = f"{package}=={version}" if version else package
        cmd = [self.config.python_path, "-m", "pip", "install", "--user", pkg_spec]

        try:
            result = await self._run_subprocess(
                cmd,
                wall_clock_timeout=self.config.max_execution_seconds,
                cwd=None,
            )
        except RuntimeError as e:
            return ActionResult(success=False, error=str(e))

        logger.info(
            "Package install attempted",
            extra={
                "employee_id": str(self.employee_id),
                "package": pkg_spec,
                "exit_code": result.exit_code,
                "duration_ms": result.duration_ms,
            },
        )

        return ActionResult(
            success=result.exit_code == 0,
            output={
                "stdout": result.stdout,
                "stderr": result.stderr,
                "exit_code": result.exit_code,
                "package": pkg_spec,
            },
            error=result.stderr if result.exit_code != 0 else None,
            metadata={"duration_ms": result.duration_ms},
        )

    # ------------------------------------------------------------------
    # Subprocess helper
    # ------------------------------------------------------------------

    async def _run_subprocess(
        self,
        cmd: list[str],
        wall_clock_timeout: int,
        cwd: str | None,
    ) -> SubprocessResult:
        """Run a command in a subprocess with timeout and output truncation.

        Args:
            cmd: Command and arguments.
            wall_clock_timeout: Wall-clock timeout in seconds.
            cwd: Working directory for the subprocess.

        Returns:
            SubprocessResult with stdout, stderr, exit_code, duration_ms.
        """
        start = time()
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
            )
        except FileNotFoundError:
            raise RuntimeError(
                f"Python interpreter not found at '{cmd[0]}'. Check ComputeConfig.python_path."
            ) from None
        except OSError as e:
            raise RuntimeError(f"Failed to start subprocess: {e}") from e

        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(),
                timeout=wall_clock_timeout,
            )
        except TimeoutError:
            logger.warning(
                "Script execution timed out, killing process",
                extra={
                    "employee_id": str(self.employee_id),
                    "timeout_seconds": wall_clock_timeout,
                },
            )
            try:
                proc.kill()
            except ProcessLookupError:
                pass  # Already exited
            except OSError as e:
                logger.error(
                    "Failed to kill timed-out process",
                    extra={"employee_id": str(self.employee_id), "error": str(e)},
                )
            try:
                await asyncio.wait_for(proc.wait(), timeout=5.0)
            except TimeoutError:
                logger.error(
                    "Timed-out process did not exit after SIGKILL",
                    extra={"employee_id": str(self.employee_id)},
                )
            duration_ms = (time() - start) * 1000
            return SubprocessResult(
                stdout="",
                stderr=f"Execution timed out after {wall_clock_timeout} seconds",
                exit_code=-1,
                duration_ms=duration_ms,
            )

        duration_ms = (time() - start) * 1000

        # Truncate output if too large
        max_bytes = self.config.max_output_bytes
        stdout_str = self._truncate_output(stdout_bytes, max_bytes)
        stderr_str = self._truncate_output(stderr_bytes, max_bytes)

        # Explicit None check — proc.returncode should always be set after
        # communicate(), but guard against unknown process state.
        exit_code = proc.returncode
        if exit_code is None:
            logger.error(
                "Subprocess returncode is None after communicate() — process state unknown",
                extra={"employee_id": str(self.employee_id), "cmd": cmd[0]},
            )
            exit_code = -2

        return SubprocessResult(
            stdout=stdout_str,
            stderr=stderr_str,
            exit_code=exit_code,
            duration_ms=duration_ms,
        )

    def _truncate_output(self, data: bytes, max_bytes: int) -> str:
        """Decode and truncate output to max_bytes."""
        if len(data) > max_bytes:
            logger.warning(
                "Subprocess output truncated",
                extra={
                    "employee_id": str(self.employee_id),
                    "output_bytes": len(data),
                    "max_bytes": max_bytes,
                },
            )
            truncated = data[:max_bytes]
            text = truncated.decode("utf-8", errors="replace")
            text += f"\n... [truncated, {len(data)} bytes total]"
            return text
        return data.decode("utf-8", errors="replace")

    # ------------------------------------------------------------------
    # Path security
    # ------------------------------------------------------------------

    def _is_inside_state_dir(self, resolved_path: Path) -> bool:
        """Check if a resolved path falls inside the .state/ directory."""
        ws_root = self._workspace_root
        if ws_root is None:
            return False
        try:
            resolved_path.relative_to(ws_root / ".state")
            return True
        except ValueError:
            return False

    def _resolve_safe_path(self, relative_path: str) -> Path:
        """Validate and resolve a relative path within the workspace.

        Same security model as WorkspaceCapability._resolve_safe_path():
        rejects empty, absolute, traversal, symlink escape, and .state/ access.

        Returns:
            The resolved absolute path within the workspace.

        Raises:
            ValueError: If path is unsafe.
        """
        ws_root, _temp_dir = self._require_initialized()

        if not relative_path:
            raise ValueError("Path cannot be empty")

        p = Path(relative_path)

        if p.is_absolute():
            raise ValueError("Absolute paths are not allowed")

        if ".." in p.parts:
            raise ValueError("Path traversal (..) is not allowed")

        full = (ws_root / p).resolve()

        # Verify containment
        try:
            full.relative_to(ws_root)
        except ValueError:
            raise ValueError("Path escapes workspace root") from None

        if self._is_inside_state_dir(full):
            raise ValueError("Access to .state/ is not allowed")

        return full

    # ------------------------------------------------------------------
    # Shutdown
    # ------------------------------------------------------------------

    async def shutdown(self) -> None:
        """Clean up temp files in .state/compute/."""
        if not self._initialized or self._temp_dir is None:
            return

        def _cleanup() -> None:
            if self._temp_dir and self._temp_dir.exists():
                failed_count = 0
                for f in self._temp_dir.iterdir():
                    if f.is_file():
                        try:
                            f.unlink()
                        except OSError as e:
                            failed_count += 1
                            logger.warning(
                                "Failed to delete temp file during shutdown",
                                extra={
                                    "employee_id": str(self.employee_id),
                                    "error": str(e),
                                },
                            )
                if failed_count:
                    logger.error(
                        f"Shutdown cleanup failed for {failed_count} temp file(s)",
                        extra={"employee_id": str(self.employee_id)},
                    )

        try:
            await asyncio.to_thread(_cleanup)
        except OSError as e:
            logger.error(
                "Failed to clean compute temp directory",
                exc_info=True,
                extra={"employee_id": str(self.employee_id), "error": str(e)},
            )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _redact_code(self, content: str) -> str:
        """Return a SHA256 hash of code content for PII-safe logging."""
        h = hashlib.sha256(content.encode()).hexdigest()[:8]
        return f"[code:{h}]"
