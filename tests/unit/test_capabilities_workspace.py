"""
Unit tests for WorkspaceCapability.

All tests use pytest's tmp_path fixture for real filesystem operations.
"""

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest

from empla.capabilities.base import (
    CAPABILITY_WORKSPACE,
    Action,
)
from empla.capabilities.workspace import (
    DEFAULT_DIRECTORIES,
    WorkspaceCapability,
    WorkspaceConfig,
)

# -------------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------------


def make_capability(
    tmp_path: Path,
    *,
    tenant_id=None,
    employee_id=None,
    config_overrides: dict | None = None,
) -> tuple[WorkspaceCapability, dict]:
    """Create a WorkspaceCapability pointed at tmp_path."""
    tid = tenant_id or uuid4()
    eid = employee_id or uuid4()
    cfg_kwargs = {"base_path": str(tmp_path)}
    if config_overrides:
        cfg_kwargs.update(config_overrides)
    config = WorkspaceConfig(**cfg_kwargs)
    cap = WorkspaceCapability(tid, eid, config)
    return cap, {"tenant_id": tid, "employee_id": eid}


def workspace_root(tmp_path: Path, tenant_id, employee_id) -> Path:
    return tmp_path / str(tenant_id) / str(employee_id)


# =========================================================================
# Config tests
# =========================================================================


class TestWorkspaceConfig:
    def test_defaults(self):
        cfg = WorkspaceConfig()
        assert cfg.base_path == "workspaces"
        assert cfg.max_file_size_mb == 50
        assert cfg.max_workspace_size_mb == 500
        assert cfg.allowed_extensions is None
        assert cfg.stale_draft_days == 3
        assert cfg.capacity_warning_percent == 80.0
        assert cfg.log_pii is False

    def test_custom_values(self):
        cfg = WorkspaceConfig(
            base_path="/custom",
            max_file_size_mb=10,
            allowed_extensions=["txt", "md"],
        )
        assert cfg.base_path == "/custom"
        assert cfg.max_file_size_mb == 10
        assert cfg.allowed_extensions == ["txt", "md"]

    def test_default_directories(self):
        cfg = WorkspaceConfig()
        assert "research" in cfg.default_directories
        assert "drafts" in cfg.default_directories
        assert "data" in cfg.default_directories

    def test_perception_paths_default(self):
        cfg = WorkspaceConfig()
        assert cfg.perception_check_paths == ["drafts", "data"]

    def test_inherits_capability_config(self):
        cfg = WorkspaceConfig(enabled=False, rate_limit=10)
        assert cfg.enabled is False
        assert cfg.rate_limit == 10


# =========================================================================
# Initialization tests
# =========================================================================


class TestWorkspaceInit:
    @pytest.mark.asyncio
    async def test_directories_created(self, tmp_path):
        cap, ids = make_capability(tmp_path)
        await cap.initialize()
        root = workspace_root(tmp_path, ids["tenant_id"], ids["employee_id"])
        for d in DEFAULT_DIRECTORIES:
            assert (root / d).is_dir(), f"Missing directory: {d}"

    @pytest.mark.asyncio
    async def test_state_dir_created(self, tmp_path):
        cap, ids = make_capability(tmp_path)
        await cap.initialize()
        root = workspace_root(tmp_path, ids["tenant_id"], ids["employee_id"])
        assert (root / ".state").is_dir()

    @pytest.mark.asyncio
    async def test_capability_type(self, tmp_path):
        cap, _ = make_capability(tmp_path)
        assert cap.capability_type == CAPABILITY_WORKSPACE

    @pytest.mark.asyncio
    async def test_repr(self, tmp_path):
        cap, ids = make_capability(tmp_path)
        r = repr(cap)
        assert "WorkspaceCapability" in r
        assert "workspace" in r
        assert str(ids["employee_id"]) in r


# =========================================================================
# Path security tests
# =========================================================================


class TestPathSecurity:
    @pytest.mark.asyncio
    async def test_traversal_blocked(self, tmp_path):
        cap, _ = make_capability(tmp_path)
        await cap.initialize()
        with pytest.raises(ValueError, match="traversal"):
            cap._resolve_safe_path("../../../etc/passwd")

    @pytest.mark.asyncio
    async def test_absolute_path_blocked(self, tmp_path):
        cap, _ = make_capability(tmp_path)
        await cap.initialize()
        with pytest.raises(ValueError, match="Absolute"):
            cap._resolve_safe_path("/etc/passwd")

    @pytest.mark.asyncio
    async def test_symlink_escape_blocked(self, tmp_path):
        cap, ids = make_capability(tmp_path)
        await cap.initialize()
        root = workspace_root(tmp_path, ids["tenant_id"], ids["employee_id"])
        # Create symlink pointing outside workspace
        link = root / "notes" / "escape_link"
        link.symlink_to("/tmp")
        with pytest.raises(ValueError, match="escapes workspace"):
            cap._resolve_safe_path("notes/escape_link/secret")

    @pytest.mark.asyncio
    async def test_state_dir_blocked(self, tmp_path):
        cap, _ = make_capability(tmp_path)
        await cap.initialize()
        with pytest.raises(ValueError, match=r"\.state"):
            cap._resolve_safe_path(".state/perception.json")

    @pytest.mark.asyncio
    async def test_valid_path_resolves(self, tmp_path):
        cap, ids = make_capability(tmp_path)
        await cap.initialize()
        result = cap._resolve_safe_path("notes/meeting.md")
        root = workspace_root(tmp_path, ids["tenant_id"], ids["employee_id"])
        assert str(result).startswith(str(root.resolve()))

    @pytest.mark.asyncio
    async def test_path_with_spaces(self, tmp_path):
        cap, _ = make_capability(tmp_path)
        await cap.initialize()
        result = cap._resolve_safe_path("notes/my meeting notes.md")
        assert result.name == "my meeting notes.md"


# =========================================================================
# read_file tests
# =========================================================================


class TestReadFile:
    @pytest.mark.asyncio
    async def test_read_success(self, tmp_path):
        cap, ids = make_capability(tmp_path)
        await cap.initialize()
        root = workspace_root(tmp_path, ids["tenant_id"], ids["employee_id"])
        (root / "notes" / "test.txt").write_text("hello world")

        action = Action(
            capability="workspace", operation="read_file", parameters={"path": "notes/test.txt"}
        )
        result = await cap._execute_action_impl(action)
        assert result.success is True
        assert result.output["content"] == "hello world"
        assert result.output["size_bytes"] > 0

    @pytest.mark.asyncio
    async def test_read_not_found(self, tmp_path):
        cap, _ = make_capability(tmp_path)
        await cap.initialize()

        action = Action(
            capability="workspace", operation="read_file", parameters={"path": "nonexistent.txt"}
        )
        result = await cap._execute_action_impl(action)
        assert result.success is False
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_read_metadata(self, tmp_path):
        cap, ids = make_capability(tmp_path)
        await cap.initialize()
        root = workspace_root(tmp_path, ids["tenant_id"], ids["employee_id"])
        (root / "data" / "report.csv").write_text("a,b,c\n1,2,3")

        action = Action(
            capability="workspace", operation="read_file", parameters={"path": "data/report.csv"}
        )
        result = await cap._execute_action_impl(action)
        assert result.success is True
        assert "modified_at" in result.output
        assert result.output["size_bytes"] == len("a,b,c\n1,2,3")

    @pytest.mark.asyncio
    async def test_read_path_traversal(self, tmp_path):
        cap, _ = make_capability(tmp_path)
        await cap.initialize()

        action = Action(
            capability="workspace", operation="read_file", parameters={"path": "../../etc/passwd"}
        )
        result = await cap._execute_action_impl(action)
        assert result.success is False
        assert "traversal" in result.error.lower()


# =========================================================================
# write_file tests
# =========================================================================


class TestWriteFile:
    @pytest.mark.asyncio
    async def test_write_success(self, tmp_path):
        cap, ids = make_capability(tmp_path)
        await cap.initialize()

        action = Action(
            capability="workspace",
            operation="write_file",
            parameters={"path": "notes/test.md", "content": "# Test"},
        )
        result = await cap._execute_action_impl(action)
        assert result.success is True
        assert result.output["path"] == "notes/test.md"

        root = workspace_root(tmp_path, ids["tenant_id"], ids["employee_id"])
        assert (root / "notes" / "test.md").read_text() == "# Test"

    @pytest.mark.asyncio
    async def test_write_creates_parent_dirs(self, tmp_path):
        cap, ids = make_capability(tmp_path)
        await cap.initialize()

        action = Action(
            capability="workspace",
            operation="write_file",
            parameters={"path": "research/deep/nested/file.txt", "content": "nested"},
        )
        result = await cap._execute_action_impl(action)
        assert result.success is True

        root = workspace_root(tmp_path, ids["tenant_id"], ids["employee_id"])
        assert (root / "research" / "deep" / "nested" / "file.txt").read_text() == "nested"

    @pytest.mark.asyncio
    async def test_write_size_limit(self, tmp_path):
        cap, _ = make_capability(tmp_path, config_overrides={"max_file_size_mb": 0})
        await cap.initialize()

        action = Action(
            capability="workspace",
            operation="write_file",
            parameters={"path": "test.txt", "content": "too big"},
        )
        result = await cap._execute_action_impl(action)
        assert result.success is False
        assert "exceeds limit" in result.error.lower()

    @pytest.mark.asyncio
    async def test_write_extension_filter(self, tmp_path):
        cap, _ = make_capability(tmp_path, config_overrides={"allowed_extensions": ["txt", "md"]})
        await cap.initialize()

        action = Action(
            capability="workspace",
            operation="write_file",
            parameters={"path": "script.py", "content": "print('hi')"},
        )
        result = await cap._execute_action_impl(action)
        assert result.success is False
        assert "not allowed" in result.error.lower()

    @pytest.mark.asyncio
    async def test_write_zero_limits_rejects(self, tmp_path):
        # Both limits set to 0 to satisfy the model_validator (file <= workspace).
        # With max_file_size_mb=0, the per-file size check rejects before the
        # workspace capacity check runs.
        cap, _ids = make_capability(
            tmp_path,
            config_overrides={"max_file_size_mb": 0, "max_workspace_size_mb": 0},
        )
        await cap.initialize()

        action = Action(
            capability="workspace",
            operation="write_file",
            parameters={"path": "test.txt", "content": "some data"},
        )
        result = await cap._execute_action_impl(action)
        assert result.success is False
        assert "exceeds limit" in result.error.lower()

    @pytest.mark.asyncio
    async def test_write_workspace_capacity_exceeded(self, tmp_path):
        """Workspace capacity check fires when file fits within file limit but exceeds total."""
        cap, ids = make_capability(
            tmp_path,
            config_overrides={"max_file_size_mb": 1, "max_workspace_size_mb": 1},
        )
        await cap.initialize()
        root = workspace_root(tmp_path, ids["tenant_id"], ids["employee_id"])

        # Pre-fill workspace close to capacity (~900KB)
        (root / "data" / "filler.txt").write_text("x" * (900 * 1024))

        # Write another 200KB — within per-file limit but exceeds 1MB workspace total
        action = Action(
            capability="workspace",
            operation="write_file",
            parameters={"path": "notes/extra.txt", "content": "y" * (200 * 1024)},
        )
        result = await cap._execute_action_impl(action)
        assert result.success is False
        assert "capacity exceeded" in result.error.lower()

    @pytest.mark.asyncio
    async def test_write_path_traversal(self, tmp_path):
        cap, _ = make_capability(tmp_path)
        await cap.initialize()

        action = Action(
            capability="workspace",
            operation="write_file",
            parameters={"path": "../../escape.txt", "content": "bad"},
        )
        result = await cap._execute_action_impl(action)
        assert result.success is False
        assert "traversal" in result.error.lower()

    @pytest.mark.asyncio
    async def test_write_overwrite_existing(self, tmp_path):
        cap, ids = make_capability(tmp_path)
        await cap.initialize()
        root = workspace_root(tmp_path, ids["tenant_id"], ids["employee_id"])
        (root / "notes" / "existing.txt").write_text("old content")

        action = Action(
            capability="workspace",
            operation="write_file",
            parameters={"path": "notes/existing.txt", "content": "new content"},
        )
        result = await cap._execute_action_impl(action)
        assert result.success is True
        assert (root / "notes" / "existing.txt").read_text() == "new content"


# =========================================================================
# list_directory tests
# =========================================================================


class TestListDirectory:
    @pytest.mark.asyncio
    async def test_list_success(self, tmp_path):
        cap, ids = make_capability(tmp_path)
        await cap.initialize()
        root = workspace_root(tmp_path, ids["tenant_id"], ids["employee_id"])
        (root / "notes" / "a.txt").write_text("aaa")
        (root / "notes" / "b.txt").write_text("bbb")

        action = Action(
            capability="workspace", operation="list_directory", parameters={"path": "notes"}
        )
        result = await cap._execute_action_impl(action)
        assert result.success is True
        names = [f["name"] for f in result.output["files"]]
        assert "a.txt" in names
        assert "b.txt" in names

    @pytest.mark.asyncio
    async def test_list_with_pattern(self, tmp_path):
        cap, ids = make_capability(tmp_path)
        await cap.initialize()
        root = workspace_root(tmp_path, ids["tenant_id"], ids["employee_id"])
        (root / "notes" / "a.txt").write_text("aaa")
        (root / "notes" / "b.md").write_text("bbb")

        action = Action(
            capability="workspace",
            operation="list_directory",
            parameters={"path": "notes", "pattern": "*.md"},
        )
        result = await cap._execute_action_impl(action)
        assert result.success is True
        names = [f["name"] for f in result.output["files"]]
        assert "b.md" in names
        assert "a.txt" not in names

    @pytest.mark.asyncio
    async def test_list_empty_dir(self, tmp_path):
        cap, _ = make_capability(tmp_path)
        await cap.initialize()

        action = Action(
            capability="workspace", operation="list_directory", parameters={"path": "templates"}
        )
        result = await cap._execute_action_impl(action)
        assert result.success is True
        assert result.output["files"] == []

    @pytest.mark.asyncio
    async def test_list_not_found(self, tmp_path):
        cap, _ = make_capability(tmp_path)
        await cap.initialize()

        action = Action(
            capability="workspace", operation="list_directory", parameters={"path": "nonexistent"}
        )
        result = await cap._execute_action_impl(action)
        assert result.success is False
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_list_path_traversal(self, tmp_path):
        cap, _ = make_capability(tmp_path)
        await cap.initialize()

        action = Action(
            capability="workspace",
            operation="list_directory",
            parameters={"path": "../../etc"},
        )
        result = await cap._execute_action_impl(action)
        assert result.success is False
        assert "traversal" in result.error.lower()

    @pytest.mark.asyncio
    async def test_list_pattern_traversal_rejected(self, tmp_path):
        cap, _ = make_capability(tmp_path)
        await cap.initialize()

        action = Action(
            capability="workspace",
            operation="list_directory",
            parameters={"path": "notes", "pattern": "../../*.txt"},
        )
        result = await cap._execute_action_impl(action)
        assert result.success is False
        assert ".." in result.error


# =========================================================================
# delete_file tests
# =========================================================================


class TestDeleteFile:
    @pytest.mark.asyncio
    async def test_delete_success(self, tmp_path):
        cap, ids = make_capability(tmp_path)
        await cap.initialize()
        root = workspace_root(tmp_path, ids["tenant_id"], ids["employee_id"])
        target = root / "notes" / "delete_me.txt"
        target.write_text("bye")

        action = Action(
            capability="workspace",
            operation="delete_file",
            parameters={"path": "notes/delete_me.txt"},
        )
        result = await cap._execute_action_impl(action)
        assert result.success is True
        assert result.output["deleted"] is True
        assert not target.exists()

    @pytest.mark.asyncio
    async def test_delete_not_found(self, tmp_path):
        cap, _ = make_capability(tmp_path)
        await cap.initialize()

        action = Action(
            capability="workspace", operation="delete_file", parameters={"path": "ghost.txt"}
        )
        result = await cap._execute_action_impl(action)
        assert result.success is False
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_delete_path_traversal(self, tmp_path):
        cap, _ = make_capability(tmp_path)
        await cap.initialize()

        action = Action(
            capability="workspace", operation="delete_file", parameters={"path": "../../etc/passwd"}
        )
        result = await cap._execute_action_impl(action)
        assert result.success is False
        assert "traversal" in result.error.lower()

    @pytest.mark.asyncio
    async def test_delete_directory_rejected(self, tmp_path):
        cap, _ = make_capability(tmp_path)
        await cap.initialize()

        action = Action(
            capability="workspace", operation="delete_file", parameters={"path": "notes"}
        )
        result = await cap._execute_action_impl(action)
        assert result.success is False
        assert "non-file" in result.error.lower()


# =========================================================================
# move_file tests
# =========================================================================


class TestMoveFile:
    @pytest.mark.asyncio
    async def test_move_success(self, tmp_path):
        cap, ids = make_capability(tmp_path)
        await cap.initialize()
        root = workspace_root(tmp_path, ids["tenant_id"], ids["employee_id"])
        (root / "drafts" / "v1.txt").write_text("draft v1")

        action = Action(
            capability="workspace",
            operation="move_file",
            parameters={"from": "drafts/v1.txt", "to": "artifacts/v1.txt"},
        )
        result = await cap._execute_action_impl(action)
        assert result.success is True
        assert result.output["new_path"] == "artifacts/v1.txt"
        assert not (root / "drafts" / "v1.txt").exists()
        assert (root / "artifacts" / "v1.txt").read_text() == "draft v1"

    @pytest.mark.asyncio
    async def test_move_creates_target_dir(self, tmp_path):
        cap, ids = make_capability(tmp_path)
        await cap.initialize()
        root = workspace_root(tmp_path, ids["tenant_id"], ids["employee_id"])
        (root / "notes" / "move_me.txt").write_text("data")

        action = Action(
            capability="workspace",
            operation="move_file",
            parameters={"from": "notes/move_me.txt", "to": "research/deep/moved.txt"},
        )
        result = await cap._execute_action_impl(action)
        assert result.success is True
        assert (root / "research" / "deep" / "moved.txt").exists()

    @pytest.mark.asyncio
    async def test_move_source_not_found(self, tmp_path):
        cap, _ = make_capability(tmp_path)
        await cap.initialize()

        action = Action(
            capability="workspace",
            operation="move_file",
            parameters={"from": "ghost.txt", "to": "notes/ghost.txt"},
        )
        result = await cap._execute_action_impl(action)
        assert result.success is False
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_move_validates_both_paths(self, tmp_path):
        cap, ids = make_capability(tmp_path)
        await cap.initialize()
        root = workspace_root(tmp_path, ids["tenant_id"], ids["employee_id"])
        (root / "notes" / "ok.txt").write_text("ok")

        action = Action(
            capability="workspace",
            operation="move_file",
            parameters={"from": "notes/ok.txt", "to": "../../escape.txt"},
        )
        result = await cap._execute_action_impl(action)
        assert result.success is False
        assert "traversal" in result.error.lower()

    @pytest.mark.asyncio
    async def test_move_source_traversal(self, tmp_path):
        cap, _ = make_capability(tmp_path)
        await cap.initialize()

        action = Action(
            capability="workspace",
            operation="move_file",
            parameters={"from": "../../etc/passwd", "to": "notes/stolen.txt"},
        )
        result = await cap._execute_action_impl(action)
        assert result.success is False
        assert "traversal" in result.error.lower()

    @pytest.mark.asyncio
    async def test_move_destination_exists(self, tmp_path):
        cap, ids = make_capability(tmp_path)
        await cap.initialize()
        root = workspace_root(tmp_path, ids["tenant_id"], ids["employee_id"])
        (root / "notes" / "a.txt").write_text("aaa")
        (root / "notes" / "b.txt").write_text("bbb")

        action = Action(
            capability="workspace",
            operation="move_file",
            parameters={"from": "notes/a.txt", "to": "notes/b.txt"},
        )
        result = await cap._execute_action_impl(action)
        assert result.success is False
        assert "already exists" in result.error.lower()


# =========================================================================
# search_files tests
# =========================================================================


class TestSearchFiles:
    @pytest.mark.asyncio
    async def test_search_match_found(self, tmp_path):
        cap, ids = make_capability(tmp_path)
        await cap.initialize()
        root = workspace_root(tmp_path, ids["tenant_id"], ids["employee_id"])
        (root / "notes" / "meeting.md").write_text(
            "Discussed pricing with Acme Corp\nNext steps: follow up"
        )

        action = Action(
            capability="workspace",
            operation="search_files",
            parameters={"query": "pricing"},
        )
        result = await cap._execute_action_impl(action)
        assert result.success is True
        assert result.output["total"] >= 1
        assert any("pricing" in m["context"].lower() for m in result.output["matches"])

    @pytest.mark.asyncio
    async def test_search_with_pattern(self, tmp_path):
        cap, ids = make_capability(tmp_path)
        await cap.initialize()
        root = workspace_root(tmp_path, ids["tenant_id"], ids["employee_id"])
        (root / "notes" / "a.md").write_text("target word here")
        (root / "notes" / "b.txt").write_text("target word here too")

        action = Action(
            capability="workspace",
            operation="search_files",
            parameters={"query": "target", "pattern": "*.md"},
        )
        result = await cap._execute_action_impl(action)
        assert result.success is True
        paths = [m["path"] for m in result.output["matches"]]
        assert any("a.md" in p for p in paths)
        assert not any("b.txt" in p for p in paths)

    @pytest.mark.asyncio
    async def test_search_returns_context(self, tmp_path):
        cap, ids = make_capability(tmp_path)
        await cap.initialize()
        root = workspace_root(tmp_path, ids["tenant_id"], ids["employee_id"])
        (root / "data" / "log.txt").write_text("line 1\nERROR: something broke\nline 3")

        action = Action(
            capability="workspace",
            operation="search_files",
            parameters={"query": "ERROR"},
        )
        result = await cap._execute_action_impl(action)
        assert result.success is True
        match = result.output["matches"][0]
        assert match["line"] == 2
        assert "something broke" in match["context"]

    @pytest.mark.asyncio
    async def test_search_no_results(self, tmp_path):
        cap, _ = make_capability(tmp_path)
        await cap.initialize()

        action = Action(
            capability="workspace",
            operation="search_files",
            parameters={"query": "xyznonexistent"},
        )
        result = await cap._execute_action_impl(action)
        assert result.success is True
        assert result.output["total"] == 0

    @pytest.mark.asyncio
    async def test_search_path_traversal(self, tmp_path):
        cap, _ = make_capability(tmp_path)
        await cap.initialize()

        action = Action(
            capability="workspace",
            operation="search_files",
            parameters={"query": "secret", "path": "../../etc"},
        )
        result = await cap._execute_action_impl(action)
        assert result.success is False
        assert "traversal" in result.error.lower()

    @pytest.mark.asyncio
    async def test_search_pattern_traversal_rejected(self, tmp_path):
        cap, _ = make_capability(tmp_path)
        await cap.initialize()

        action = Action(
            capability="workspace",
            operation="search_files",
            parameters={"query": "secret", "pattern": "../../*.txt"},
        )
        result = await cap._execute_action_impl(action)
        assert result.success is False
        assert ".." in result.error


# =========================================================================
# get_workspace_status tests
# =========================================================================


class TestGetWorkspaceStatus:
    @pytest.mark.asyncio
    async def test_status_populated(self, tmp_path):
        cap, ids = make_capability(tmp_path)
        await cap.initialize()
        root = workspace_root(tmp_path, ids["tenant_id"], ids["employee_id"])
        (root / "notes" / "file1.txt").write_text("hello")
        (root / "data" / "file2.csv").write_text("a,b,c")

        action = Action(capability="workspace", operation="get_workspace_status", parameters={})
        result = await cap._execute_action_impl(action)
        assert result.success is True
        assert result.output["total_files"] >= 2
        assert result.output["total_size_mb"] >= 0
        assert result.output["max_size_mb"] == 500

    @pytest.mark.asyncio
    async def test_status_empty_workspace(self, tmp_path):
        cap, _ = make_capability(tmp_path)
        await cap.initialize()

        action = Action(capability="workspace", operation="get_workspace_status", parameters={})
        result = await cap._execute_action_impl(action)
        assert result.success is True
        # Only .state/perception.json might exist if shutdown was called, but not here
        # Just verify structure
        assert "total_files" in result.output
        assert "recent_changes" in result.output


# =========================================================================
# Perception tests
# =========================================================================


class TestPerception:
    @pytest.mark.asyncio
    async def test_perceive_not_initialized(self, tmp_path):
        cap, _ = make_capability(tmp_path)
        # Don't initialize
        observations = await cap.perceive()
        assert observations == []

    @pytest.mark.asyncio
    async def test_perceive_stale_drafts(self, tmp_path):
        cap, ids = make_capability(tmp_path, config_overrides={"stale_draft_days": 0})
        await cap.initialize()
        root = workspace_root(tmp_path, ids["tenant_id"], ids["employee_id"])

        # Create a file and backdate its mtime
        draft = root / "drafts" / "old_draft.md"
        draft.write_text("stale content")
        old_time = (datetime.now(UTC) - timedelta(days=5)).timestamp()
        os.utime(draft, (old_time, old_time))

        observations = await cap.perceive()
        stale = [o for o in observations if o.observation_type == "stale_draft"]
        assert len(stale) >= 1
        assert stale[0].priority == 3

    @pytest.mark.asyncio
    async def test_perceive_new_data_file(self, tmp_path):
        cap, ids = make_capability(tmp_path)
        await cap.initialize()
        root = workspace_root(tmp_path, ids["tenant_id"], ids["employee_id"])

        # First perception pass — seeds the mtime cache
        await cap.perceive()

        # Write a new file in data/
        (root / "data" / "new_report.csv").write_text("x,y\n1,2")

        observations = await cap.perceive()
        new_data = [o for o in observations if o.observation_type == "new_data_file"]
        assert len(new_data) >= 1

    @pytest.mark.asyncio
    async def test_perceive_near_capacity(self, tmp_path):
        # Tiny workspace so we can fill it easily
        cap, ids = make_capability(
            tmp_path,
            config_overrides={
                "max_file_size_mb": 1,
                "max_workspace_size_mb": 1,  # 1 MB
                "capacity_warning_percent": 1.0,  # Warn at 1% = ~10KB
            },
        )
        await cap.initialize()
        root = workspace_root(tmp_path, ids["tenant_id"], ids["employee_id"])

        # Write enough data to exceed 1% of 1MB (i.e., > ~10KB)
        (root / "data" / "big.txt").write_text("x" * 20000)

        observations = await cap.perceive()
        cap_warns = [o for o in observations if o.observation_type == "workspace_near_capacity"]
        assert len(cap_warns) == 1
        assert cap_warns[0].priority == 4
        assert cap_warns[0].requires_action is True

    @pytest.mark.asyncio
    async def test_perceive_no_observations(self, tmp_path):
        cap, _ = make_capability(tmp_path, config_overrides={"stale_draft_days": 999})
        await cap.initialize()

        observations = await cap.perceive()
        # Fresh workspace with high stale threshold — no stale drafts, no new data, no capacity issues
        assert observations == []

    @pytest.mark.asyncio
    async def test_perceive_state_persisted(self, tmp_path):
        cap, ids = make_capability(tmp_path)
        await cap.initialize()
        root = workspace_root(tmp_path, ids["tenant_id"], ids["employee_id"])

        (root / "data" / "tracked.txt").write_text("initial")
        await cap.perceive()
        await cap.shutdown()

        # Re-create capability and re-init — state should be loaded
        cap2, _ = make_capability(
            tmp_path,
            tenant_id=ids["tenant_id"],
            employee_id=ids["employee_id"],
        )
        await cap2.initialize()
        assert cap2._last_perception_mtimes != {}


# =========================================================================
# Unknown operation
# =========================================================================


class TestUnknownOperation:
    @pytest.mark.asyncio
    async def test_unknown_operation(self, tmp_path):
        cap, _ = make_capability(tmp_path)
        await cap.initialize()

        action = Action(capability="workspace", operation="fly_to_moon", parameters={})
        result = await cap._execute_action_impl(action)
        assert result.success is False
        assert "Unknown operation" in result.error


# =========================================================================
# Parameter validation tests
# =========================================================================


class TestParameterValidation:
    @pytest.mark.asyncio
    async def test_missing_path_for_read(self, tmp_path):
        cap, _ = make_capability(tmp_path)
        await cap.initialize()

        action = Action(capability="workspace", operation="read_file", parameters={})
        result = await cap._execute_action_impl(action)
        assert result.success is False
        assert "missing required parameters" in result.error.lower()
        assert "path" in result.error

    @pytest.mark.asyncio
    async def test_missing_content_for_write(self, tmp_path):
        cap, _ = make_capability(tmp_path)
        await cap.initialize()

        action = Action(
            capability="workspace",
            operation="write_file",
            parameters={"path": "notes/test.md"},
        )
        result = await cap._execute_action_impl(action)
        assert result.success is False
        assert "missing required parameters" in result.error.lower()
        assert "content" in result.error

    @pytest.mark.asyncio
    async def test_missing_from_for_move(self, tmp_path):
        cap, _ = make_capability(tmp_path)
        await cap.initialize()

        action = Action(
            capability="workspace",
            operation="move_file",
            parameters={"to": "notes/dest.txt"},
        )
        result = await cap._execute_action_impl(action)
        assert result.success is False
        assert "from" in result.error

    @pytest.mark.asyncio
    async def test_missing_query_for_search(self, tmp_path):
        cap, _ = make_capability(tmp_path)
        await cap.initialize()

        action = Action(capability="workspace", operation="search_files", parameters={})
        result = await cap._execute_action_impl(action)
        assert result.success is False
        assert "query" in result.error


# =========================================================================
# Config validation tests
# =========================================================================


class TestConfigValidation:
    def test_negative_file_size_rejected(self):
        with pytest.raises(ValueError):
            WorkspaceConfig(max_file_size_mb=-1)

    def test_negative_workspace_size_rejected(self):
        with pytest.raises(ValueError):
            WorkspaceConfig(max_workspace_size_mb=-1)

    def test_capacity_percent_over_100_rejected(self):
        with pytest.raises(ValueError):
            WorkspaceConfig(capacity_warning_percent=101.0)

    def test_file_size_exceeds_workspace_rejected(self):
        with pytest.raises(ValueError, match="cannot exceed"):
            WorkspaceConfig(max_file_size_mb=100, max_workspace_size_mb=50)

    def test_zero_limits_valid(self):
        cfg = WorkspaceConfig(max_file_size_mb=0, max_workspace_size_mb=0)
        assert cfg.max_file_size_mb == 0
        assert cfg.max_workspace_size_mb == 0


# =========================================================================
# Empty path test
# =========================================================================


class TestEmptyPath:
    @pytest.mark.asyncio
    async def test_empty_path_rejected(self, tmp_path):
        cap, _ = make_capability(tmp_path)
        await cap.initialize()

        action = Action(
            capability="workspace",
            operation="read_file",
            parameters={"path": ""},
        )
        result = await cap._execute_action_impl(action)
        assert result.success is False
        assert "empty" in result.error.lower()


# =========================================================================
# Shutdown
# =========================================================================


class TestShutdown:
    @pytest.mark.asyncio
    async def test_shutdown_persists_state(self, tmp_path):
        cap, ids = make_capability(tmp_path)
        await cap.initialize()

        cap._last_perception_mtimes = {"data/test.txt": 12345.0}
        await cap.shutdown()

        root = workspace_root(tmp_path, ids["tenant_id"], ids["employee_id"])
        state_file = root / ".state" / "perception.json"
        assert state_file.exists()
        data = json.loads(state_file.read_text())
        assert data["data/test.txt"] == 12345.0

    @pytest.mark.asyncio
    async def test_shutdown_before_init(self, tmp_path):
        cap, _ = make_capability(tmp_path)
        # Should not raise
        await cap.shutdown()


# =========================================================================
# PII redaction
# =========================================================================


class TestRedaction:
    @pytest.mark.asyncio
    async def test_redact_path(self, tmp_path):
        cap, _ = make_capability(tmp_path)
        result = cap._redact_path(Path("/some/secret/path"))
        assert result.startswith("[path:")
        assert len(result) == len("[path:") + 8 + 1  # 8 hex chars + ]

    @pytest.mark.asyncio
    async def test_redact_none(self, tmp_path):
        cap, _ = make_capability(tmp_path)
        assert cap._redact_path(None) == "[redacted]"
