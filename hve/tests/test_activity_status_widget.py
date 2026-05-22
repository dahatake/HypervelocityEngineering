"""test_activity_status_widget.py — ActivityStatusWidget 単体テスト。"""

from __future__ import annotations

import unittest


try:
    import PySide6  # noqa: F401
    from PySide6.QtWidgets import QApplication

    _PYSIDE6 = True
except Exception:
    _PYSIDE6 = False


_app = None


def _ensure_app():
    global _app
    if _app is None:
        from PySide6.QtWidgets import QApplication

        _app = QApplication.instance() or QApplication([])
    return _app


@unittest.skipUnless(_PYSIDE6, "PySide6 が無い環境では skip")
class TestActivityStatusWidget(unittest.TestCase):
    def setUp(self) -> None:
        _ensure_app()
        from hve.gui.workbench_widgets import ActivityStatusWidget

        self.w = ActivityStatusWidget()
        # 周期 timer は副作用を避けるため停止
        self.w._tick_timer.stop()

    def tearDown(self) -> None:
        self.w._tick_timer.stop()
        self.w.deleteLater()

    def test_initial_render_empty_plan(self) -> None:
        self.assertIn("ワークフロー: 0/0", self.w._summary_label.text())
        self.assertEqual(self.w._tree.topLevelItemCount(), 0)

    def test_set_plan_builds_hierarchy(self) -> None:
        plan = [
            {
                "workflow_id": "WF-01",
                "workflow_name": "要件定義",
                "steps": [("S1", "業務分析"), ("S2", "UC抽出")],
            },
            {
                "workflow_id": "WF-02",
                "workflow_name": "設計",
                "steps": [("S1", "サービス設計")],
            },
        ]
        wf_status = {"WF-01": "実行中", "WF-02": ""}
        step_status = {
            "WF-01": {"S1": "完了", "S2": "実行中"},
            "WF-02": {"S1": ""},
        }
        sub_status = {
            "WF-01": {
                "S2": [
                    ("sub1", "Sub-agent: foo", "実行中"),
                    ("sub2", "Sub-agent: bar", "完了"),
                ]
            }
        }
        self.w.set_plan(plan, wf_status, step_status, sub_status)

        self.assertEqual(self.w._tree.topLevelItemCount(), 2)
        wf1 = self.w._tree.topLevelItem(0)
        self.assertIn("WF-01", wf1.text(0))
        self.assertIn("要件定義", wf1.text(0))
        # 実行中 → 🟡
        self.assertIn("🟡", wf1.text(0))
        self.assertEqual(wf1.childCount(), 2)
        s2 = wf1.child(1)
        self.assertIn("S2", s2.text(0))
        self.assertEqual(s2.childCount(), 2)
        sub1 = s2.child(0)
        self.assertIn("foo", sub1.text(0))
        # ネスト上限 3 → サブタスクには子を作らない
        self.assertEqual(sub1.childCount(), 0)

        # サマリ: WF 0/2 完了, 現在 WF-01 のステップ 1/2 完了
        summary = self.w._summary_label.text()
        self.assertIn("ワークフロー: 0/2", summary)
        self.assertIn("ステップ: 1/2", summary)

    def test_summary_progresses_on_workflow_done(self) -> None:
        plan = [
            {
                "workflow_id": "WF-01",
                "workflow_name": "A",
                "steps": [("S1", "x")],
            },
            {
                "workflow_id": "WF-02",
                "workflow_name": "B",
                "steps": [("S1", "y"), ("S2", "z")],
            },
        ]
        wf_status = {"WF-01": "完了", "WF-02": "実行中"}
        step_status = {
            "WF-01": {"S1": "完了"},
            "WF-02": {"S1": "完了", "S2": "実行中"},
        }
        self.w.set_plan(plan, wf_status, step_status, {})
        summary = self.w._summary_label.text()
        # ステップは現在の WF (WF-02) のもの
        self.assertIn("ワークフロー: 1/2", summary)
        self.assertIn("ステップ: 1/2", summary)

    def test_status_emoji_mapping(self) -> None:
        from hve.gui.workbench_widgets import _ACTIVITY_EMOJI, _normalize_status

        self.assertEqual(_normalize_status(""), "pending")
        self.assertEqual(_normalize_status("実行中"), "running")
        self.assertEqual(_normalize_status("完了"), "done")
        self.assertEqual(_normalize_status("失敗"), "failed")
        self.assertEqual(_ACTIVITY_EMOJI["pending"], "⚪")
        self.assertEqual(_ACTIVITY_EMOJI["running"], "🟡")
        self.assertEqual(_ACTIVITY_EMOJI["done"], "🟢")
        self.assertEqual(_ACTIVITY_EMOJI["failed"], "🔴")

    def test_reset_clears_state(self) -> None:
        plan = [
            {
                "workflow_id": "WF-01",
                "workflow_name": "A",
                "steps": [("S1", "x")],
            }
        ]
        self.w.set_plan(plan, {"WF-01": "実行中"}, {"WF-01": {"S1": "実行中"}}, {})
        self.assertEqual(self.w._tree.topLevelItemCount(), 1)
        self.assertIsNotNone(self.w._global_started_at)

        self.w.reset()
        self.assertEqual(self.w._tree.topLevelItemCount(), 0)
        self.assertIsNone(self.w._global_started_at)
        self.assertEqual(self.w._timings, {})
        self.assertIn("ワークフロー: 0/0", self.w._summary_label.text())

    def test_skipped_counted_as_done(self) -> None:
        plan = [
            {
                "workflow_id": "WF-01",
                "workflow_name": "A",
                "steps": [("S1", "x"), ("S2", "y")],
            }
        ]
        self.w.set_plan(
            plan,
            {"WF-01": "実行中"},
            {"WF-01": {"S1": "スキップ", "S2": "完了"}},
            {},
        )
        # スキップも完了扱い → 2/2
        self.assertIn("ステップ: 2/2", self.w._summary_label.text())

    def test_default_theme_is_dark(self) -> None:
        from hve.gui.workbench_widgets import _ACTIVITY_THEMES

        self.assertEqual(self.w._theme, "dark")
        self.assertIn("#252526", _ACTIVITY_THEMES["dark"]["tree"])

    def test_set_theme_light(self) -> None:
        self.w.set_theme("light")
        self.assertEqual(self.w._theme, "light")
        # ライトテーマの背景色を反映
        self.assertIn("#f3f3f3", self.w._tree.styleSheet())

    def test_set_theme_invalid_ignored(self) -> None:
        self.w.set_theme("light")
        self.w.set_theme("solarized")  # 不正値
        self.assertEqual(self.w._theme, "light")

    def test_init_with_theme_light(self) -> None:
        from hve.gui.workbench_widgets import ActivityStatusWidget

        w2 = ActivityStatusWidget(theme="light")
        w2._tick_timer.stop()
        self.assertEqual(w2._theme, "light")
        self.assertIn("#f3f3f3", w2._tree.styleSheet())
        w2.deleteLater()


if __name__ == "__main__":
    unittest.main()
