from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from brain_ds.mcp.security import (
    TOOL_SCHEMAS,
    SecurityError,
    ValidationError,
    error_boundary,
    resolve_store_path,
    validate_tool_input,
)
from brain_ds.store.errors import StoreError


class ResolveStorePathTests(unittest.TestCase):
    def test_resolve_store_path_returns_store_db_inside_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store_path = root / ".brain_ds" / "store.db"
            store_path.parent.mkdir(parents=True, exist_ok=True)
            store_path.write_text("db")

            resolved = resolve_store_path(str(root))

            self.assertEqual(resolved, store_path.resolve())

    def test_resolve_store_path_rejects_path_traversal_input(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            outside = base / "outside"
            outside.mkdir()
            (outside / ".brain_ds").mkdir()
            (outside / ".brain_ds" / "store.db").write_text("db")

            traversal = base / "outside" / ".." / "outside"
            with self.assertRaisesRegex(SecurityError, "Path traversal is not allowed"):
                resolve_store_path(str(traversal))

    def test_resolve_store_path_rejects_nonexistent_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "does-not-exist"
            with self.assertRaisesRegex(SecurityError, "Project root does not exist"):
                resolve_store_path(str(missing))

    def test_resolve_store_path_bootstraps_missing_dir_on_fresh_install(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            resolved = resolve_store_path(str(root))

            self.assertTrue((root / ".brain_ds").is_dir())
            self.assertEqual(resolved, (root / ".brain_ds" / "store.db").resolve(strict=False))

    def test_resolve_store_path_allows_missing_store_db_when_dir_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".brain_ds").mkdir()

            resolved = resolve_store_path(str(root))

            self.assertEqual(resolved, (root / ".brain_ds" / "store.db").resolve(strict=False))

    def test_resolve_store_path_rejects_symlinked_store_escaping_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "root"
            root.mkdir()
            (root / ".brain_ds").mkdir()
            outside_dir = Path(tmp) / "outside"
            outside_dir.mkdir()
            outside_store = outside_dir / "store.db"
            outside_store.write_text("db")

            try:
                (root / ".brain_ds" / "store.db").symlink_to(outside_store)
            except OSError as exc:
                self.skipTest(f"Symlink creation unavailable on this platform: {exc}")

            with self.assertRaisesRegex(SecurityError, "Store path escapes project root"):
                resolve_store_path(str(root))

    def test_resolve_store_path_rejects_symlinked_dot_brain_ds_escaping_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "root"
            root.mkdir()
            outside_dir = Path(tmp) / "outside"
            outside_dir.mkdir()
            (outside_dir / "store.db").write_text("db")

            try:
                (root / ".brain_ds").symlink_to(outside_dir, target_is_directory=True)
            except OSError as exc:
                self.skipTest(f"Symlink creation unavailable on this platform: {exc}")

            with self.assertRaisesRegex(SecurityError, "Store path escapes canonical root"):
                resolve_store_path(str(root))


class ValidateToolInputTests(unittest.TestCase):
    def setUp(self) -> None:
        self.schema = {
            "type": "object",
            "required": ["graph_id", "query"],
            "properties": {
                "graph_id": {"type": "string"},
                "query": {"type": "string"},
                "limit": {"type": "number"},
            },
            "additionalProperties": False,
        }

    def test_rejects_unknown_field(self) -> None:
        with self.assertRaises(ValidationError) as ctx:
            validate_tool_input("search_graph", {"graph_id": "g", "query": "x", "extra": 1}, self.schema)

        self.assertEqual(ctx.exception.code, -32602)
        self.assertIn("Unknown parameter: extra", ctx.exception.message)

    def test_rejects_missing_required_field(self) -> None:
        with self.assertRaises(ValidationError) as ctx:
            validate_tool_input("search_graph", {"graph_id": "g"}, self.schema)

        self.assertEqual(ctx.exception.code, -32602)
        self.assertIn("Missing required parameter: query", ctx.exception.message)

    def test_rejects_type_mismatch(self) -> None:
        with self.assertRaises(ValidationError) as ctx:
            validate_tool_input("search_graph", {"graph_id": "g", "query": 42}, self.schema)

        self.assertEqual(ctx.exception.code, -32602)
        self.assertIn("Expected string for query", ctx.exception.message)

    def test_accepts_valid_input_unchanged(self) -> None:
        params = {"graph_id": "g", "query": "abc", "limit": 3}

        result = validate_tool_input("search_graph", params, self.schema)

        self.assertIs(result, params)
        self.assertEqual(result, params)

    def test_tool_schemas_declares_core_tools(self) -> None:
        for name in ["list_nodes", "get_node", "search_graph", "update_node", "add_edge"]:
            self.assertIn(name, TOOL_SCHEMAS)


class ErrorBoundaryTests(unittest.TestCase):
    def test_returns_data_dict_on_success(self) -> None:
        @error_boundary
        def handler() -> dict[str, str]:
            return {"ok": "yes"}

        self.assertEqual(handler(), {"ok": "yes"})

    def test_validation_error_passes_through_code_and_message(self) -> None:
        @error_boundary
        def handler() -> dict[str, str]:
            raise ValidationError(code=-32602, message="Missing required parameter: graph_id")

        self.assertEqual(handler(), {"code": -32602, "message": "Missing required parameter: graph_id"})

    def test_store_error_is_sanitized_to_server_error(self) -> None:
        @error_boundary
        def handler() -> dict[str, str]:
            raise StoreError("graph failure")

        self.assertEqual(handler(), {"code": -32000, "message": "Store operation failed"})

    def test_unexpected_exception_becomes_internal_error_without_repr(self) -> None:
        @error_boundary
        def handler() -> dict[str, str]:
            raise RuntimeError("secret-token")

        result = handler()

        self.assertEqual(result["code"], -32000)
        self.assertEqual(result["message"], "Internal error")
        self.assertNotIn("secret-token", result["message"])
        self.assertNotIn("RuntimeError", result["message"])


if __name__ == "__main__":
    unittest.main()
