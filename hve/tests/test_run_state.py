"""test_run_state.py — Phase 1 Run State Manager のユニットテスト。

DoD（Phase 1）:
- 全テストが PASS する
- save → load round-trip が成立する
- 機密情報が state.json にシリアライズされない
- 破損 state.json で list_resumable_runs が落ちない
"""

from __future__ import annotations

import io
import json
import os
import re
import sys
import tempfile
import threading
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config import SDKConfig  # type: ignore[import-not-found]
import run_state as run_state_module  # type: ignore[import-not-found]
from run_state import (  # type: ignore[import-not-found]
    DEFAULT_RUNS_DIR,
    SCHEMA_VERSION,
    HostInfo,
    RunState,
    StepState,
    _get_copilot_sdk_version,
    _SAFE_CONFIG_FIELDS,
    _major_version,
    _safe_run_id_component,
    is_resumable,
    list_resumable_runs,
    to_safe_config_dict,
)


# ---------------------------------------------------------------------------
# 共通ヘルパー
# ---------------------------------------------------------------------------

def _make_state(
    work_dir: Path,
    run_id: str = "20260507T000000-aaaaaa",
    workflow_id: str = "akm",
    config: SDKConfig | None = None,
) -> RunState:
    return RunState.new(
        run_id=run_id,
        workflow_id=workflow_id,
        config=config or SDKConfig(),
        params={"foo": "bar", "n": 3},
        selected_step_ids=["1.1", "1.2", "2.1"],
        work_dir=work_dir,
    )


# ---------------------------------------------------------------------------
# Run State の I/O
# ---------------------------------------------------------------------------

class TestRunStateIO(unittest.TestCase):
    """新規作成 → save → load round-trip と原子的書き込みを検証。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.work_dir = Path(self._tmp.name) / "runs"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_new_run_creates_state_with_defaults(self) -> None:
        state = _make_state(self.work_dir)
        self.assertEqual(state.schema_version, SCHEMA_VERSION)
        self.assertEqual(state.workflow_id, "akm")
        self.assertEqual(state.status, "pending")
        self.assertEqual(state.total_count, 3)
        self.assertEqual(state.completed_count, 0)
        self.assertEqual(set(state.step_states.keys()), {"1.1", "1.2", "2.1"})
        for st in state.step_states.values():
            self.assertEqual(st.status, "pending")
            self.assertIsNone(st.session_id)
        # host info
        self.assertTrue(state.host.platform)
        self.assertTrue(state.host.python_version)
        self.assertTrue(state.host.hostname_hash)
        self.assertEqual(len(state.host.hostname_hash), 16)

    def test_new_requires_run_id(self) -> None:
        with self.assertRaises(ValueError):
            RunState.new(run_id="", workflow_id="akm", work_dir=self.work_dir)

    def test_state_path_uses_work_dir_and_run_id(self) -> None:
        state = _make_state(self.work_dir, run_id="20260507T000000-abc123")
        expected = self.work_dir / "20260507T000000-abc123" / "state.json"
        self.assertEqual(state.state_path, expected)

    def test_save_creates_state_json(self) -> None:
        state = _make_state(self.work_dir)
        state.save()
        self.assertTrue(state.state_path.exists())
        # 内容が JSON として読み込める
        with state.state_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data["run_id"], state.run_id)
        self.assertEqual(data["workflow_id"], "akm")
        self.assertEqual(data["schema_version"], SCHEMA_VERSION)
        # _work_dir は serialize されない
        self.assertNotIn("_work_dir", data)

    def test_save_load_roundtrip(self) -> None:
        original = _make_state(self.work_dir)
        original.save()

        loaded = RunState.load(original.run_id, work_dir=self.work_dir)
        self.assertEqual(loaded.run_id, original.run_id)
        self.assertEqual(loaded.workflow_id, original.workflow_id)
        self.assertEqual(loaded.selected_step_ids, original.selected_step_ids)
        self.assertEqual(loaded.params_snapshot, original.params_snapshot)
        self.assertEqual(set(loaded.step_states.keys()), set(original.step_states.keys()))
        self.assertEqual(loaded.host.hostname_hash, original.host.hostname_hash)
        self.assertEqual(loaded.host.platform, original.host.platform)

    def test_save_writes_then_atomic_replace(self) -> None:
        """save 中に .tmp ファイルが残らないことを確認。"""
        state = _make_state(self.work_dir)
        state.save()
        # tmp ファイルが残っていない
        tmp_files = list(state.state_path.parent.glob("*.tmp"))
        self.assertEqual(tmp_files, [])

    def test_save_updates_last_updated_at(self) -> None:
        state = _make_state(self.work_dir)
        first = state.last_updated_at
        state.save()
        self.assertNotEqual(state.last_updated_at, "")
        # save 後はタイムスタンプが (>=) 更新される
        self.assertGreaterEqual(state.last_updated_at, first)

    def test_update_step_persists_immediately(self) -> None:
        state = _make_state(self.work_dir)
        state.save()

        state.update_step("1.1", status="completed", elapsed_seconds=12.5)
        # 即座に永続化されているはず
        loaded = RunState.load(state.run_id, work_dir=self.work_dir)
        self.assertEqual(loaded.step_states["1.1"].status, "completed")
        self.assertEqual(loaded.step_states["1.1"].elapsed_seconds, 12.5)
        self.assertEqual(loaded.completed_count, 1)

    def test_update_step_unknown_field_raises(self) -> None:
        state = _make_state(self.work_dir)
        with self.assertRaises(AttributeError):
            state.update_step("1.1", nonexistent_field="x")

    def test_update_step_invalid_status_raises(self) -> None:
        state = _make_state(self.work_dir)
        with self.assertRaises(ValueError):
            state.update_step("1.1", status="bogus")

    def test_update_step_creates_unknown_step(self) -> None:
        """DAG 動的追加のため未知ステップでも保存できる。"""
        state = _make_state(self.work_dir)
        state.update_step("9.9", status="completed")
        loaded = RunState.load(state.run_id, work_dir=self.work_dir)
        self.assertIn("9.9", loaded.step_states)
        self.assertEqual(loaded.step_states["9.9"].status, "completed")

    def test_save_is_atomic_under_concurrent_write(self) -> None:
        """並行 save() で常に valid な JSON が読める。

        Windows の os.replace は writer 同士・reader/writer の同時実行で
        短時間 PermissionError を起こすが、save() 内のリトライで吸収される。
        本テストは「reader が valid JSON を読めること」と「writer が最終的に
        成功すること」を保証する（短時間の競合エラーは想定内）。
        """
        import time as _time

        state = _make_state(self.work_dir)
        state.save()

        write_errors: list[Exception] = []
        read_errors: list[Exception] = []
        invalid_json_count = 0
        lock_for_count = threading.Lock()

        def writer() -> None:
            try:
                for _ in range(20):
                    state.update_step("1.1", status="running", elapsed_seconds=1.0)
                    state.update_step("1.1", status="completed", elapsed_seconds=2.0)
            except Exception as exc:  # pragma: no cover - 失敗時のみ
                write_errors.append(exc)

        def reader() -> None:
            nonlocal invalid_json_count
            for _ in range(40):
                if not state.state_path.exists():
                    continue
                # Windows での reader/writer 競合は実用上 list_resumable_runs と
                # 同様にリトライで吸収する。
                for attempt in range(5):
                    try:
                        with state.state_path.open("r", encoding="utf-8") as f:
                            json.load(f)  # 不正 JSON だと例外
                        break
                    except PermissionError:
                        _time.sleep(0.01)
                    except json.JSONDecodeError as exc:  # pragma: no cover
                        with lock_for_count:
                            invalid_json_count += 1
                        read_errors.append(exc)
                        break
                    except Exception as exc:  # pragma: no cover
                        read_errors.append(exc)
                        break

        threads = [
            threading.Thread(target=writer),
            threading.Thread(target=writer),
            threading.Thread(target=reader),
            threading.Thread(target=reader),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(write_errors, [], f"writer で例外発生: {write_errors}")
        self.assertEqual(invalid_json_count, 0, "reader が壊れた JSON を読んだ")
        # 最終状態が正しく save されている
        loaded = RunState.load(state.run_id, work_dir=self.work_dir)
        self.assertEqual(loaded.step_states["1.1"].status, "completed")

    def test_load_missing_file_raises(self) -> None:
        with self.assertRaises(FileNotFoundError):
            RunState.load("nonexistent-run-id", work_dir=self.work_dir)

    def test_default_runs_dir_is_session_state_runs(self) -> None:
        # DEFAULT_RUNS_DIR は <repo-root>/session-state/runs を指す（CWD 非依存）
        from run_state import _resolve_repo_root
        self.assertEqual(DEFAULT_RUNS_DIR, _resolve_repo_root() / "session-state" / "runs")


# ---------------------------------------------------------------------------
# 機密情報の漏えい防止
# ---------------------------------------------------------------------------

class TestNoSecretsInState(unittest.TestCase):
    """_SAFE_CONFIG_FIELDS ホワイトリスト方式で機密が漏れないことを検証。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.work_dir = Path(self._tmp.name) / "runs"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _serialized(self, state: RunState) -> str:
        return json.dumps(state.to_dict(), ensure_ascii=False)

    def test_github_token_not_in_snapshot(self) -> None:
        cfg = SDKConfig(github_token="ghp_secret_12345")
        state = _make_state(self.work_dir, config=cfg)
        self.assertNotIn("github_token", state.config_snapshot)
        text = self._serialized(state)
        self.assertNotIn("ghp_secret_12345", text)

    def test_repo_url_not_in_snapshot(self) -> None:
        cfg = SDKConfig(repo="acme/private-repo")
        state = _make_state(self.work_dir, config=cfg)
        self.assertNotIn("repo", state.config_snapshot)
        self.assertNotIn("acme/private-repo", self._serialized(state))

    def test_cli_path_not_in_snapshot(self) -> None:
        cfg = SDKConfig(cli_path="/home/secret/.local/bin/copilot")
        state = _make_state(self.work_dir, config=cfg)
        self.assertNotIn("cli_path", state.config_snapshot)
        self.assertNotIn("/home/secret", self._serialized(state))

    def test_cli_url_not_in_snapshot(self) -> None:
        cfg = SDKConfig(cli_url="https://internal.corp/copilot")
        state = _make_state(self.work_dir, config=cfg)
        self.assertNotIn("cli_url", state.config_snapshot)
        self.assertNotIn("internal.corp", self._serialized(state))

    def test_mcp_servers_with_api_key_not_in_snapshot(self) -> None:
        cfg = SDKConfig(mcp_servers={
            "github": {
                "type": "http",
                "url": "https://api.githubcopilot.com/mcp/",
                "headers": {"Authorization": "Bearer ghs_super_secret"},
            }
        })
        state = _make_state(self.work_dir, config=cfg)
        self.assertNotIn("mcp_servers", state.config_snapshot)
        self.assertNotIn("ghs_super_secret", self._serialized(state))

    def test_workiq_tenant_id_not_in_snapshot(self) -> None:
        """テナント ID は組織情報のため snapshot から除外（許可リストに含めていない）。"""
        cfg = SDKConfig(workiq_tenant_id="00000000-1111-2222-3333-444444444444")
        state = _make_state(self.work_dir, config=cfg)
        self.assertNotIn("workiq_tenant_id", state.config_snapshot)
        self.assertNotIn("00000000-1111", self._serialized(state))

    def test_safe_fields_are_preserved(self) -> None:
        """許可フィールドは正しく snapshot される。"""
        cfg = SDKConfig(model="claude-opus-4.7", base_branch="develop", max_parallel=5)
        state = _make_state(self.work_dir, config=cfg)
        self.assertEqual(state.config_snapshot.get("model"), "claude-opus-4.7")
        self.assertEqual(state.config_snapshot.get("base_branch"), "develop")
        self.assertEqual(state.config_snapshot.get("max_parallel"), 5)

    def test_to_safe_config_dict_with_dict_input(self) -> None:
        out = to_safe_config_dict({"model": "x", "github_token": "T", "repo": "r"})
        self.assertEqual(out, {"model": "x"})

    def test_to_safe_config_dict_with_none(self) -> None:
        self.assertEqual(to_safe_config_dict(None), {})

    def test_safe_config_fields_excludes_known_secrets(self) -> None:
        for field in ("github_token", "repo", "cli_path", "cli_url", "mcp_servers"):
            self.assertNotIn(field, _SAFE_CONFIG_FIELDS)


# ---------------------------------------------------------------------------
# list_resumable_runs
# ---------------------------------------------------------------------------

class TestListResumableRuns(unittest.TestCase):
    """work/runs/ の列挙 / 破損ファイルの skip / ソート順を検証。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.work_dir = Path(self._tmp.name) / "runs"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_returns_empty_when_dir_missing(self) -> None:
        self.assertEqual(list_resumable_runs(self.work_dir), [])

    def test_returns_empty_when_no_runs(self) -> None:
        self.work_dir.mkdir(parents=True)
        self.assertEqual(list_resumable_runs(self.work_dir), [])

    def test_returns_all_runs_with_state_json(self) -> None:
        for rid in ("20260101T000000-aaaaaa", "20260102T000000-bbbbbb"):
            _make_state(self.work_dir, run_id=rid).save()
        runs = list_resumable_runs(self.work_dir)
        self.assertEqual(len(runs), 2)

    def test_handles_corrupt_state_json_gracefully(self) -> None:
        # 1 つは正常、1 つは破損
        _make_state(self.work_dir, run_id="20260101T000000-aaaaaa").save()
        bad_dir = self.work_dir / "20260102T000000-bbbbbb"
        bad_dir.mkdir(parents=True)
        (bad_dir / "state.json").write_text("{ invalid json", encoding="utf-8")

        # 例外を投げず、1 件だけ返る
        runs = list_resumable_runs(self.work_dir)
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0].run_id, "20260101T000000-aaaaaa")

    def test_corrupt_state_json_warns_and_skips(self) -> None:
        _make_state(self.work_dir, run_id="20260101T000000-aaaaaa").save()
        bad_dir = self.work_dir / "20260102T000000-bbbbbb"
        bad_dir.mkdir(parents=True)
        (bad_dir / "state.json").write_text("{ invalid json", encoding="utf-8")

        err = io.StringIO()
        with redirect_stderr(err):
            runs = list_resumable_runs(self.work_dir)
        self.assertEqual([r.run_id for r in runs], ["20260101T000000-aaaaaa"])
        self.assertIn("WARN", err.getvalue())
        self.assertIn("skip", err.getvalue())

    def test_skips_directories_without_state_json(self) -> None:
        (self.work_dir / "empty-dir").mkdir(parents=True)
        _make_state(self.work_dir, run_id="20260101T000000-aaaaaa").save()
        runs = list_resumable_runs(self.work_dir)
        self.assertEqual(len(runs), 1)

    def test_sorts_by_last_updated_at_desc(self) -> None:
        s_old = _make_state(self.work_dir, run_id="20260101T000000-aaaaaa")
        s_old.last_updated_at = "2026-01-01T00:00:00+00:00"
        s_old.created_at = "2026-01-01T00:00:00+00:00"
        s_old.save()
        # save() で last_updated_at が上書きされる → 直接書き戻して順序を検証
        with s_old.state_path.open("r", encoding="utf-8") as f:
            data_old = json.load(f)
        data_old["last_updated_at"] = "2026-01-01T00:00:00+00:00"
        s_old.state_path.write_text(json.dumps(data_old), encoding="utf-8")

        s_new = _make_state(self.work_dir, run_id="20260102T000000-bbbbbb")
        s_new.save()
        with s_new.state_path.open("r", encoding="utf-8") as f:
            data_new = json.load(f)
        data_new["last_updated_at"] = "2026-12-31T00:00:00+00:00"
        s_new.state_path.write_text(json.dumps(data_new), encoding="utf-8")

        runs = list_resumable_runs(self.work_dir)
        self.assertEqual([r.run_id for r in runs],
                         ["20260102T000000-bbbbbb", "20260101T000000-aaaaaa"])


# ---------------------------------------------------------------------------
# is_resumable
# ---------------------------------------------------------------------------

class TestIsResumable(unittest.TestCase):
    """status と SDK バージョン互換による判定を検証。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.work_dir = Path(self._tmp.name) / "runs"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _state(self, status: str, sdk_version: str) -> RunState:
        s = _make_state(self.work_dir)
        s.status = status
        s.host.copilot_sdk_version = sdk_version
        return s

    def test_completed_run_not_resumable(self) -> None:
        # 現環境の SDK バージョンと一致しても status=completed は再開不可
        current = HostInfo.current().copilot_sdk_version
        self.assertFalse(is_resumable(self._state("completed", current)))

    def test_pending_run_not_resumable(self) -> None:
        current = HostInfo.current().copilot_sdk_version
        self.assertFalse(is_resumable(self._state("pending", current)))

    def test_paused_run_resumable(self) -> None:
        current = HostInfo.current().copilot_sdk_version
        self.assertTrue(is_resumable(self._state("paused", current)))

    def test_running_run_resumable(self) -> None:
        current = HostInfo.current().copilot_sdk_version
        self.assertTrue(is_resumable(self._state("running", current)))

    def test_failed_run_resumable(self) -> None:
        current = HostInfo.current().copilot_sdk_version
        self.assertTrue(is_resumable(self._state("failed", current)))

    def test_sdk_version_major_mismatch_not_resumable(self) -> None:
        """保存時 1.x → 現在 2.x のような major 不一致は再開不可。"""
        # _major_version を一致させない値を設定
        # 現在のバージョン取得結果に対して別 major を設定する
        current = HostInfo.current().copilot_sdk_version
        current_major = _major_version(current)
        # 現在の major と異なるダミー major を生成
        try:
            other_major_int = (int(current_major) + 1) if current_major.isdigit() else 999
        except ValueError:
            other_major_int = 999
        saved = f"{other_major_int}.0.0"
        self.assertFalse(is_resumable(self._state("paused", saved)))

    def test_returns_false_for_none(self) -> None:
        self.assertFalse(is_resumable(None))  # type: ignore[arg-type]

    def test_is_resumable_uses_copilot_sdk_version_helper(self) -> None:
        state = self._state("paused", "1.0.0")
        with mock.patch.object(run_state_module, "_get_copilot_sdk_version", return_value="2.0.0") as patched:
            self.assertFalse(is_resumable(state))
        patched.assert_called_once()


class TestGetCopilotSdkVersion(unittest.TestCase):
    def test_get_copilot_sdk_version_returns_first_match(self) -> None:
        with mock.patch.object(run_state_module, "_get_package_version") as patched:
            patched.side_effect = lambda name, fallback="": "0.9.1" if name == "copilot-sdk" else ""
            self.assertEqual(_get_copilot_sdk_version(), "0.9.1")
            self.assertEqual(patched.call_count, 1)

    def test_get_copilot_sdk_version_falls_through_to_second_candidate(self) -> None:
        with mock.patch.object(run_state_module, "_get_package_version") as patched:
            patched.side_effect = lambda name, fallback="": (
                "" if name == "copilot-sdk" else ("0.8.0" if name == "github-copilot-sdk" else "")
            )
            self.assertEqual(_get_copilot_sdk_version(), "0.8.0")
            self.assertEqual(patched.call_count, 2)

    def test_get_copilot_sdk_version_returns_unknown_when_all_missing(self) -> None:
        with mock.patch.object(run_state_module, "_get_package_version", return_value="unknown") as patched:
            self.assertEqual(_get_copilot_sdk_version(), "unknown")
            self.assertEqual(patched.call_count, 3)


# ---------------------------------------------------------------------------
# 補助関数
# ---------------------------------------------------------------------------

class TestSafeRunIdComponent(unittest.TestCase):
    def test_normal_id_passes_through(self) -> None:
        self.assertEqual(_safe_run_id_component("20260507T000000-abc123"),
                         "20260507T000000-abc123")

    def test_path_traversal_chars_removed(self) -> None:
        # ".." やスラッシュ等は除去される
        cleaned = _safe_run_id_component("../../etc/passwd-abc")
        self.assertNotIn("..", cleaned)
        self.assertNotIn("/", cleaned)

    def test_empty_raises(self) -> None:
        with self.assertRaises(ValueError):
            _safe_run_id_component("")

    def test_only_unsafe_chars_raises(self) -> None:
        with self.assertRaises(ValueError):
            _safe_run_id_component("///....")


class TestMajorVersion(unittest.TestCase):
    def test_simple(self) -> None:
        self.assertEqual(_major_version("1.2.3"), "1")

    def test_with_prerelease(self) -> None:
        self.assertEqual(_major_version("2.0.0-alpha.1"), "2")

    def test_with_build_metadata(self) -> None:
        self.assertEqual(_major_version("3.0.0+build.5"), "3")

    def test_unknown(self) -> None:
        self.assertEqual(_major_version("unknown"), "unknown")

    def test_empty(self) -> None:
        self.assertEqual(_major_version(""), "")


class TestStepStateValidation(unittest.TestCase):
    def test_invalid_status_raises(self) -> None:
        with self.assertRaises(ValueError):
            StepState(status="bogus")

    def test_error_summary_truncated(self) -> None:
        long = "x" * 1000
        st = StepState(status="failed", error_summary=long)
        self.assertEqual(len(st.error_summary or ""), 500)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
