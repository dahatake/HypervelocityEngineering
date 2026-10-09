"""Unit/integration tests for the Studio core."""
import json
import http.client
import sys
import tempfile
import threading
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
from eabk_model import build_model, management_paths
from studio import HOST, PORT, StudioState, make_handler
from http.server import ThreadingHTTPServer


class StudioCoreTests(unittest.TestCase):
    def make_repo(self, root: Path) -> None:
        (root / "docs").mkdir()
        (root / "docs" / "requirements-definition.md").write_text(
            "#### FR-001 Model\n- 受入基準 AC-001: Traverse\n", encoding="utf-8")
        (root / "docs" / "catalog.md").write_text(
            "| 要求 ID | 題名 | 決定状態 | 実装ファイル | テスト | 使っている共通部品 |\n"
            "|---|---|---|---|---|---|\n"
            "| FR-001 | Model | 承認済み | `src/model.py` | `tests/test_model.py` | Model |\n",
            encoding="utf-8")

    # FR-001 AC-001
    def test_model_links_requirement_catalog_file_and_test(self):
        with tempfile.TemporaryDirectory() as value:
            root = Path(value); self.make_repo(root)
            model = build_model(root)
            self.assertEqual(model["reqs"][0]["id"], "FR-001")
            kinds = {edge["kind"] for edge in model["edges"]}
            self.assertTrue({"catalog", "file"} <= kinds)

    # FR-013 AC-013; NFR-SEC-002 AC-024
    def test_model_build_is_read_only(self):
        with tempfile.TemporaryDirectory() as value:
            root = Path(value); self.make_repo(root)
            before = {p: (p.stat().st_mtime_ns, p.read_bytes()) for p in management_paths(root) if p.exists()}
            build_model(root)
            self.assertEqual(before, {p: (p.stat().st_mtime_ns, p.read_bytes()) for p in before})

    # NFR-SEC-001 AC-023
    def test_server_constants_are_loopback_and_default_port(self):
        self.assertEqual((HOST, PORT), ("127.0.0.1", 8765))

    # FR-013 AC-013; NFR-SEC-001 AC-023
    def test_http_boundary_rejects_foreign_host(self):
        with tempfile.TemporaryDirectory() as value:
            root = Path(value); self.make_repo(root)
            server = ThreadingHTTPServer((HOST, 0), make_handler(StudioState(root)))
            worker = threading.Thread(target=server.serve_forever, daemon=True); worker.start()
            try:
                client = http.client.HTTPConnection(HOST, server.server_port, timeout=2)
                client.request("GET", "/api/model", headers={"Host": "evil.example"})
                self.assertEqual(client.getresponse().status, 403)
            finally:
                server.shutdown(); server.server_close(); worker.join()

    # NFR-OPS-001 AC-026; NFR-OPS-004 AC-029
    def test_custom_management_paths_are_honored(self):
        with tempfile.TemporaryDirectory() as value:
            root = Path(value); (root / "custom").mkdir()
            (root / "scripts").mkdir()
            (root / "scripts" / "ebak.config.json").write_text(json.dumps({"management_files": {
                "requirements": "custom/req.md", "catalog": "custom/cat.md"}}), encoding="utf-8")
            (root / "custom" / "req.md").write_text("#### FR-X Custom\n", encoding="utf-8")
            (root / "custom" / "cat.md").write_text("# Catalog\n", encoding="utf-8")
            self.assertEqual(build_model(root)["reqs"][0]["id"], "FR-X")


if __name__ == "__main__":
    unittest.main()
