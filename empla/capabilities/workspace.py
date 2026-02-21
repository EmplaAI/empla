"""
Workspace Capability

Gives digital employees access to their local filesystem — their "desk" for
research notes, drafts, artifacts, scripts, and templates. Each employee gets
an isolated workspace directory (base_path / tenant_id / employee_id).

This capability operates on the local filesystem only. Remote storage is out
of scope.

Operations:
- read_file: Read file contents
- write_file: Write/overwrite a file
- list_directory: List directory contents with optional glob pattern
- delete_file: Delete a file
- move_file: Move/rename a file
- search_files: Search file contents by text query
- get_workspace_status: Get workspace usage summary
"""

import asyncio
import hashlib
import json
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

from pydantic import Field, model_validator

from empla.capabilities.base import (
    CAPABILITY_WORKSPACE,
    Action,
    ActionResult,
    BaseCapability,
    CapabilityConfig,
    Observation,
)

logger = logging.getLogger(__name__)

DEFAULT_DIRECTORIES = [
    "research",
    "research/prospects",
    "research/market",
    "drafts",
    "artifacts",
    "artifacts/reports",
    "artifacts/presentations",
    "scripts",
    "templates",
    "notes",
    "data",
]

# Required parameters for each workspace operation
_REQUIRED_PARAMS: dict[str, list[str]] = {
    "read_file": ["path"],
    "write_file": ["path", "content"],
    "list_directory": [],
    "delete_file": ["path"],
    "move_file": ["from", "to"],
    "search_files": ["query"],
    "get_workspace_status": [],
}


class WorkspaceConfig(CapabilityConfig):
    """Configuration for the workspace capability."""

    base_path: str = "workspaces"
    """Root directory for all workspaces"""

    default_directories: list[str] = Field(default_factory=lambda: list(DEFAULT_DIRECTORIES))
    """Directories to create on initialization"""

    max_file_size_mb: int = Field(default=50, ge=0)
    """Maximum size for a single file in MB"""

    max_workspace_size_mb: int = Field(default=500, ge=0)
    """Maximum total workspace size in MB"""

    allowed_extensions: list[str] | None = None
    """Allowed file extensions (None = all allowed)"""

    perception_check_paths: list[str] = Field(default=["drafts", "data"])
    """Directories to monitor during perception"""

    stale_draft_days: int = Field(default=3, ge=0)
    """Days after which a draft is considered stale"""

    capacity_warning_percent: float = Field(default=80.0, ge=0.0, le=100.0)
    """Warn when workspace usage exceeds this percent of max"""

    log_pii: bool = False
    """If True, log full filesystem paths in log messages; if False, replace with hashed redactions"""

    @model_validator(mode="after")
    def _validate_size_limits(self) -> "WorkspaceConfig":
        if self.max_file_size_mb > self.max_workspace_size_mb:
            raise ValueError(
                f"max_file_size_mb ({self.max_file_size_mb}) cannot exceed "
                f"max_workspace_size_mb ({self.max_workspace_size_mb})"
            )
        return self


class WorkspaceCapability(BaseCapability):
    """
    Workspace capability — local filesystem access for digital employees.

    Each employee gets an isolated directory tree under:
        base_path / tenant_id / employee_id /

    Security:
    - All paths validated through _resolve_safe_path() before I/O
    - Path traversal (../) blocked
    - Absolute paths rejected
    - Symlink escape prevented via resolve()
    - Internal .state/ directory blocked from external access

    Limits:
    - Max file size enforced on write
    - Max workspace capacity enforced on write
    - Optional file extension allowlist
    """

    def __init__(
        self,
        tenant_id: UUID,
        employee_id: UUID,
        config: WorkspaceConfig,
    ) -> None:
        super().__init__(tenant_id, employee_id, config)
        self.config: WorkspaceConfig = config
        self._workspace_root: Path | None = None
        self._last_perception_mtimes: dict[str, float] = {}
        self._perception_seeded: bool = False

    @property
    def capability_type(self) -> str:
        return CAPABILITY_WORKSPACE

    def _require_initialized(self) -> Path:
        """Return workspace root or raise if not initialized."""
        if self._workspace_root is None:
            raise RuntimeError("WorkspaceCapability must be initialized before use")
        return self._workspace_root

    async def initialize(self) -> None:
        """Create workspace directory tree and load persisted state."""
        root = Path(self.config.base_path) / str(self.tenant_id) / str(self.employee_id)

        def _create_dirs() -> None:
            root.mkdir(parents=True, exist_ok=True)
            for d in self.config.default_directories:
                (root / d).mkdir(parents=True, exist_ok=True)
            (root / ".state").mkdir(parents=True, exist_ok=True)

        await asyncio.to_thread(_create_dirs)
        self._workspace_root = root.resolve()

        # Load persisted perception state
        state_file = self._workspace_root / ".state" / "perception.json"
        try:
            data = await asyncio.to_thread(state_file.read_text)
            self._last_perception_mtimes = json.loads(data)
        except FileNotFoundError:
            pass  # No persisted state — starting fresh
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            logger.warning(
                "Corrupted perception state file, starting fresh",
                exc_info=True,
                extra={"employee_id": str(self.employee_id), "error": str(e)},
            )
        except OSError as e:
            logger.error(
                "Cannot read perception state file",
                exc_info=True,
                extra={"employee_id": str(self.employee_id), "error": str(e)},
            )

        self._initialized = True

        logger.info(
            "Workspace capability initialized",
            extra={
                "employee_id": str(self.employee_id),
                "workspace_root": (
                    str(self._workspace_root)
                    if self.config.log_pii
                    else self._redact_path(self._workspace_root)
                ),
            },
        )

    # ------------------------------------------------------------------
    # Path security
    # ------------------------------------------------------------------

    def _is_inside_workspace(self, resolved_path: Path) -> bool:
        """Check if a resolved path is contained within the workspace root."""
        ws_root = self._require_initialized()
        try:
            resolved_path.relative_to(ws_root)
            return True
        except ValueError:
            return False

    def _is_inside_state_dir(self, resolved_path: Path) -> bool:
        """Check if a resolved path falls inside the .state/ directory."""
        ws_root = self._require_initialized()
        try:
            resolved_path.relative_to(ws_root / ".state")
            return True
        except ValueError:
            return False

    def _resolve_safe_path(self, relative_path: str) -> Path:
        """
        Validate and resolve a relative path within the workspace.

        Returns:
            The resolved absolute path within the workspace.

        Raises:
            ValueError: If path is unsafe (empty, absolute, traversal,
                symlink escape, or .state access)
        """
        ws_root = self._require_initialized()

        if not relative_path:
            raise ValueError("Path cannot be empty")

        p = Path(relative_path)

        # Reject absolute paths
        if p.is_absolute():
            raise ValueError("Absolute paths are not allowed")

        # Reject .. in any component
        if ".." in p.parts:
            raise ValueError("Path traversal (..) is not allowed")

        # Resolve full path (follows symlinks) and verify containment
        full = (ws_root / p).resolve()
        if not self._is_inside_workspace(full):
            raise ValueError("Path escapes workspace root")

        if self._is_inside_state_dir(full):
            raise ValueError("Access to .state/ is not allowed")

        return full

    def _validate_glob_pattern(self, pattern: str) -> str | None:
        """Validate a glob pattern, returning an error message if invalid."""
        if ".." in pattern:
            return "Pattern cannot contain '..'"
        return None

    # ------------------------------------------------------------------
    # Perception
    # ------------------------------------------------------------------

    async def perceive(self) -> list[Observation]:
        if not self._initialized:
            logger.warning(
                "Workspace perception called before initialization",
                extra={"employee_id": str(self.employee_id)},
            )
            return []

        observations: list[Observation] = []
        ws_root = self._require_initialized()

        try:
            # 1. Stale drafts
            drafts_dir = ws_root / "drafts"
            stale_draft_days = self.config.stale_draft_days

            def _scan_stale_drafts() -> list[Observation]:
                if not drafts_dir.exists():
                    return []
                result: list[Observation] = []
                cutoff = datetime.now(UTC) - timedelta(days=stale_draft_days)
                for f in drafts_dir.iterdir():
                    if f.is_file():
                        mtime = datetime.fromtimestamp(f.stat().st_mtime, tz=UTC)
                        if mtime < cutoff:
                            result.append(
                                Observation(
                                    employee_id=self.employee_id,
                                    tenant_id=self.tenant_id,
                                    observation_type="stale_draft",
                                    source="workspace",
                                    content={
                                        "path": str(f.relative_to(ws_root)),
                                        "modified_at": mtime.isoformat(),
                                        "days_stale": (datetime.now(UTC) - mtime).days,
                                    },
                                    priority=3,
                                    requires_action=False,
                                )
                            )
                return result

            observations.extend(await asyncio.to_thread(_scan_stale_drafts))

            # 2. New data files
            check_paths = self.config.perception_check_paths
            perception_seeded = self._perception_seeded
            last_mtimes = self._last_perception_mtimes

            def _scan_new_data() -> tuple[list[Observation], dict[str, float]]:
                result: list[Observation] = []
                mtime_updates: dict[str, float] = {}
                for check_path in check_paths:
                    check_dir = ws_root / check_path
                    if not check_dir.exists():
                        continue
                    for f in check_dir.iterdir():
                        if not f.is_file():
                            continue
                        rel = str(f.relative_to(ws_root))
                        current_mtime = f.stat().st_mtime
                        prev_mtime = last_mtimes.get(rel)
                        if prev_mtime is None or current_mtime > prev_mtime:
                            # Only report new/changed files after the first perception pass
                            # has established baseline mtimes (seed pass records but doesn't report)
                            if perception_seeded:
                                result.append(
                                    Observation(
                                        employee_id=self.employee_id,
                                        tenant_id=self.tenant_id,
                                        observation_type="new_data_file",
                                        source="workspace",
                                        content={
                                            "path": rel,
                                            "size_bytes": f.stat().st_size,
                                        },
                                        priority=5,
                                        requires_action=False,
                                    )
                                )
                            mtime_updates[rel] = current_mtime
                return result, mtime_updates

            new_data_obs, mtime_updates = await asyncio.to_thread(_scan_new_data)
            observations.extend(new_data_obs)
            self._last_perception_mtimes.update(mtime_updates)

            # 3. Workspace near capacity
            total_size = await self._get_total_size_bytes()
            max_bytes = self.config.max_workspace_size_mb * 1024 * 1024
            if max_bytes > 0:
                usage_pct = (total_size / max_bytes) * 100
                if usage_pct >= self.config.capacity_warning_percent:
                    observations.append(
                        Observation(
                            employee_id=self.employee_id,
                            tenant_id=self.tenant_id,
                            observation_type="workspace_near_capacity",
                            source="workspace",
                            content={
                                "usage_percent": round(usage_pct, 1),
                                "total_size_mb": round(total_size / (1024 * 1024), 2),
                                "max_size_mb": self.config.max_workspace_size_mb,
                            },
                            priority=4,
                            requires_action=True,
                        )
                    )

            self._perception_seeded = True

        except Exception as e:
            logger.error(
                "Workspace perception failed",
                exc_info=True,
                extra={
                    "employee_id": str(self.employee_id),
                    "error": str(e),
                },
            )

        return observations

    # ------------------------------------------------------------------
    # Action dispatch
    # ------------------------------------------------------------------

    async def _execute_action_impl(self, action: Action) -> ActionResult:
        operation = action.operation
        params = action.parameters

        # Validate required parameters
        required = _REQUIRED_PARAMS.get(operation)
        if required is None:
            return ActionResult(success=False, error=f"Unknown operation: {operation}")

        missing = [p for p in required if p not in params]
        if missing:
            return ActionResult(
                success=False,
                error=f"Operation '{operation}' missing required parameters: {missing}",
            )

        if operation == "read_file":
            return await self._read_file(params["path"])

        if operation == "write_file":
            return await self._write_file(params["path"], params["content"])

        if operation == "list_directory":
            return await self._list_directory(
                params.get("path", ""),
                params.get("pattern"),
            )

        if operation == "delete_file":
            return await self._delete_file(params["path"])

        if operation == "move_file":
            return await self._move_file(params["from"], params["to"])

        if operation == "search_files":
            return await self._search_files(
                params["query"],
                params.get("path"),
                params.get("pattern"),
            )

        if operation == "get_workspace_status":
            return await self._get_workspace_status()

        # Unreachable: _REQUIRED_PARAMS.get(operation) already rejects unknown operations above.
        # Kept as a defensive fallback.
        return ActionResult(
            success=False, error=f"Unknown operation: {operation}"
        )  # pragma: no cover

    # ------------------------------------------------------------------
    # Operations
    # ------------------------------------------------------------------

    async def _read_file(self, path: str) -> ActionResult:
        try:
            full = self._resolve_safe_path(path)
        except ValueError as e:
            return ActionResult(success=False, error=str(e))

        def _read() -> tuple[str, int, float] | None:
            if not full.exists() or not full.is_file():
                return None
            content = full.read_text(encoding="utf-8")
            stat = full.stat()
            return content, stat.st_size, stat.st_mtime

        try:
            result = await asyncio.to_thread(_read)
        except UnicodeDecodeError:
            return ActionResult(
                success=False,
                error=f"Cannot read '{path}': file is not valid UTF-8 text",
            )
        except FileNotFoundError:
            return ActionResult(success=False, error=f"File not found: {path}")
        except PermissionError:
            return ActionResult(success=False, error=f"Permission denied reading '{path}'")
        except OSError as e:
            return ActionResult(success=False, error=f"I/O error reading '{path}': {e}")

        if result is None:
            return ActionResult(success=False, error=f"File not found: {path}")

        content, size, mtime = result

        logger.debug(
            "File read",
            extra={
                "employee_id": str(self.employee_id),
                "path": path if self.config.log_pii else self._redact_path(full),
                "size_bytes": size,
            },
        )

        return ActionResult(
            success=True,
            output={
                "content": content,
                "size_bytes": size,
                "modified_at": datetime.fromtimestamp(mtime, tz=UTC).isoformat(),
            },
        )

    async def _write_file(self, path: str, content: str) -> ActionResult:
        try:
            full = self._resolve_safe_path(path)
        except ValueError as e:
            return ActionResult(success=False, error=str(e))

        if self.config.allowed_extensions is not None:
            ext = full.suffix.lstrip(".")
            if ext not in self.config.allowed_extensions:
                return ActionResult(
                    success=False,
                    error=f"Extension '{ext}' is not allowed. Allowed: {self.config.allowed_extensions}",
                )

        content_bytes = content.encode("utf-8")
        max_file_bytes = self.config.max_file_size_mb * 1024 * 1024
        if len(content_bytes) > max_file_bytes:
            return ActionResult(
                success=False,
                error=f"File size ({len(content_bytes)} bytes) exceeds limit ({max_file_bytes} bytes)",
            )

        current_size = await self._get_total_size_bytes()

        # Account for overwrite: subtract existing file size if it exists
        def _existing_size() -> int:
            try:
                return full.stat().st_size if full.exists() else 0
            except OSError:
                return 0

        existing_size = await asyncio.to_thread(_existing_size)
        new_total = current_size - existing_size + len(content_bytes)
        max_ws_bytes = self.config.max_workspace_size_mb * 1024 * 1024
        if new_total > max_ws_bytes:
            return ActionResult(
                success=False,
                error=f"Workspace capacity exceeded ({new_total} bytes > {max_ws_bytes} bytes)",
            )

        def _write() -> int:
            full.parent.mkdir(parents=True, exist_ok=True)
            full.write_bytes(content_bytes)
            return len(content_bytes)

        try:
            size = await asyncio.to_thread(_write)
        except PermissionError:
            return ActionResult(success=False, error=f"Permission denied writing to '{path}'")
        except OSError as e:
            return ActionResult(success=False, error=f"I/O error writing '{path}': {e}")

        logger.info(
            "File written",
            extra={
                "employee_id": str(self.employee_id),
                "path": path if self.config.log_pii else self._redact_path(full),
                "size_bytes": size,
            },
        )

        return ActionResult(
            success=True,
            output={
                "path": path,
                "size_bytes": size,
            },
        )

    async def _list_directory(self, path: str, pattern: str | None = None) -> ActionResult:
        ws_root = self._require_initialized()

        if path:
            try:
                full = self._resolve_safe_path(path)
            except ValueError as e:
                return ActionResult(success=False, error=str(e))
        else:
            full = ws_root

        if not full.exists() or not full.is_dir():
            return ActionResult(success=False, error=f"Directory not found: {path}")

        if pattern:
            err = self._validate_glob_pattern(pattern)
            if err:
                return ActionResult(success=False, error=err)

        def _list() -> list[dict[str, Any]]:
            entries = list(full.glob(pattern)) if pattern else list(full.iterdir())

            safe_entries = []
            for e in entries:
                resolved = e.resolve()
                if self._is_inside_workspace(resolved) and not self._is_inside_state_dir(resolved):
                    safe_entries.append(e)

            files: list[dict[str, Any]] = []
            for entry in sorted(safe_entries, key=lambda e: e.name):
                try:
                    stat = entry.stat()
                except OSError:
                    continue
                files.append(
                    {
                        "name": entry.name,
                        "size_bytes": stat.st_size if entry.is_file() else 0,
                        "modified_at": datetime.fromtimestamp(stat.st_mtime, tz=UTC).isoformat(),
                        "is_dir": entry.is_dir(),
                    }
                )
            return files

        try:
            entries = await asyncio.to_thread(_list)
        except ValueError as e:
            return ActionResult(success=False, error=f"Invalid glob pattern '{pattern}': {e}")
        except OSError as e:
            return ActionResult(success=False, error=f"Error listing directory '{path}': {e}")

        return ActionResult(
            success=True,
            output={"files": entries},
        )

    async def _delete_file(self, path: str) -> ActionResult:
        try:
            full = self._resolve_safe_path(path)
        except ValueError as e:
            return ActionResult(success=False, error=str(e))

        if not full.exists():
            return ActionResult(success=False, error=f"File not found: {path}")

        if not full.is_file():
            return ActionResult(success=False, error=f"Cannot delete non-file: {path}")

        try:
            await asyncio.to_thread(full.unlink)
        except FileNotFoundError:
            return ActionResult(success=False, error=f"File not found: {path}")
        except PermissionError:
            return ActionResult(success=False, error=f"Permission denied deleting '{path}'")
        except OSError as e:
            return ActionResult(success=False, error=f"I/O error deleting '{path}': {e}")

        logger.info(
            "File deleted",
            extra={
                "employee_id": str(self.employee_id),
                "path": path if self.config.log_pii else self._redact_path(full),
            },
        )

        return ActionResult(success=True, output={"deleted": True})

    async def _move_file(self, from_path: str, to_path: str) -> ActionResult:
        try:
            src = self._resolve_safe_path(from_path)
        except ValueError as e:
            return ActionResult(success=False, error=f"Source path error: {e}")

        try:
            dst = self._resolve_safe_path(to_path)
        except ValueError as e:
            return ActionResult(success=False, error=f"Destination path error: {e}")

        if not src.exists():
            return ActionResult(success=False, error=f"Source not found: {from_path}")

        if not src.is_file():
            return ActionResult(success=False, error=f"Cannot move non-file: {from_path}")

        if dst.exists():
            return ActionResult(
                success=False,
                error=f"Destination already exists: {to_path}",
            )

        def _move() -> None:
            dst.parent.mkdir(parents=True, exist_ok=True)
            src.rename(dst)

        try:
            await asyncio.to_thread(_move)
        except OSError as e:
            return ActionResult(
                success=False,
                error=f"Failed to move '{from_path}' to '{to_path}': {e}",
            )

        logger.info(
            "File moved",
            extra={
                "employee_id": str(self.employee_id),
                "from": from_path if self.config.log_pii else self._redact_path(src),
                "to": to_path if self.config.log_pii else self._redact_path(dst),
            },
        )

        return ActionResult(success=True, output={"new_path": to_path})

    async def _search_files(
        self,
        query: str,
        path: str | None = None,
        pattern: str | None = None,
    ) -> ActionResult:
        ws_root = self._require_initialized()

        if path:
            try:
                search_root = self._resolve_safe_path(path)
            except ValueError as e:
                return ActionResult(success=False, error=str(e))
        else:
            search_root = ws_root

        if pattern:
            err = self._validate_glob_pattern(pattern)
            if err:
                return ActionResult(success=False, error=err)

        def _search() -> list[dict[str, Any]]:
            matches: list[dict[str, Any]] = []

            files = list(search_root.rglob(pattern)) if pattern else list(search_root.rglob("*"))

            for f in files:
                if not f.is_file():
                    continue
                resolved = f.resolve()
                if self._is_inside_state_dir(resolved):
                    continue
                if not self._is_inside_workspace(resolved):
                    continue

                try:
                    content = f.read_text(encoding="utf-8")
                except UnicodeDecodeError:
                    continue
                except PermissionError:
                    logger.warning(
                        "Permission denied reading file during search, skipping",
                        extra={
                            "employee_id": str(self.employee_id),
                            "path": str(f.relative_to(ws_root))
                            if self.config.log_pii
                            else "[redacted]",
                        },
                    )
                    continue

                for i, line in enumerate(content.splitlines(), 1):
                    if query.lower() in line.lower():
                        matches.append(
                            {
                                "path": str(f.relative_to(ws_root)),
                                "line": i,
                                "context": line.strip(),
                            }
                        )
                        if len(matches) >= 50:
                            return matches
            return matches

        try:
            results = await asyncio.to_thread(_search)
        except OSError as e:
            return ActionResult(success=False, error=f"Error searching files: {e}")

        return ActionResult(
            success=True,
            output={"matches": results, "total": len(results)},
        )

    async def _get_workspace_status(self) -> ActionResult:
        ws_root = self._require_initialized()

        def _status() -> dict[str, Any]:
            total_files = 0
            total_size = 0
            recent_changes: list[dict[str, Any]] = []
            cutoff = datetime.now(UTC) - timedelta(hours=24)

            for f in ws_root.rglob("*"):
                if not f.is_file():
                    continue
                if self._is_inside_state_dir(f):
                    continue

                try:
                    stat = f.stat()
                except OSError:
                    continue

                total_files += 1
                total_size += stat.st_size

                mtime = datetime.fromtimestamp(stat.st_mtime, tz=UTC)
                if mtime > cutoff:
                    recent_changes.append(
                        {
                            "path": str(f.relative_to(ws_root)),
                            "modified_at": mtime.isoformat(),
                            "size_bytes": stat.st_size,
                        }
                    )

            # Sort recent by most recent first
            recent_changes.sort(key=lambda x: x["modified_at"], reverse=True)

            return {
                "total_files": total_files,
                "total_size_mb": round(total_size / (1024 * 1024), 2),
                "max_size_mb": self.config.max_workspace_size_mb,
                "recent_changes": recent_changes[:20],
            }

        status = await asyncio.to_thread(_status)

        return ActionResult(success=True, output=status)

    # ------------------------------------------------------------------
    # Shutdown
    # ------------------------------------------------------------------

    async def shutdown(self) -> None:
        """Persist perception state to .state/ directory."""
        if not self._initialized or self._workspace_root is None:
            return

        state_file = self._workspace_root / ".state" / "perception.json"
        try:
            data = json.dumps(self._last_perception_mtimes)
            await asyncio.to_thread(state_file.write_text, data)
        except (TypeError, ValueError) as e:
            logger.error(
                "Failed to serialize perception state",
                exc_info=True,
                extra={"employee_id": str(self.employee_id), "error": str(e)},
            )
        except OSError as e:
            logger.error(
                "Failed to write perception state to disk",
                exc_info=True,
                extra={"employee_id": str(self.employee_id), "error": str(e)},
            )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _get_total_size_bytes(self) -> int:
        ws_root = self._require_initialized()

        def _calc() -> int:
            total = 0
            for f in ws_root.rglob("*"):
                if not f.is_file():
                    continue
                if self._is_inside_state_dir(f):
                    continue
                try:
                    total += f.stat().st_size
                except OSError:
                    continue
            return total

        return await asyncio.to_thread(_calc)

    def _redact_path(self, path: Path | None) -> str:
        if path is None:
            return "[redacted]"
        h = hashlib.sha256(str(path).encode()).hexdigest()[:8]
        return f"[path:{h}]"
