"""FooterWidget の Elapsed / Step Elapsed フリーズ動作テスト。

回帰防止対象のバグ:
- 全タスク完了後 (mark_all_done / mark_aborted) も Workflow Elapsed が
  カウントアップを継続していた。
- Step 完了 (set_step_status "done") 後も Step Elapsed が増え続けていた。

修正の要点 (workbench_widgets.py FooterWidget._update):
- all_done=True かつ task_tree.root.finished_at がある場合は end_time を固定。
- 表示中 Step の task_tree ノード finished_at がある場合は step end_time を固定。

このテストでは time.monotonic を monkeypatch して仮想時間を制御する。
"""

from __future__ import annotations

import os
import sys
import re
import time

import pytest

# ヘッドレス環境用に offscreen platform を強制
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from hve.gui.workbench_state import WorkbenchState, StepView  # noqa: E402
from hve.gui.workbench_widgets import FooterWidget  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication(sys.argv)
    return app


def _make_state() -> WorkbenchState:
    s = WorkbenchState(workflow_id="wf", run_id="r1", model="gpt-x")
    # default_factory は monkeypatch 前の time.monotonic を捕捉済みのため、
    # 仮想時間 0.0 起点に明示的に揃える (root.started_at は使わないので未変更)。
    s.workflow_started_at = 0.0
    return s


_ELAPSED_RE = re.compile(
    r"Elapsed:</span>\s*<span[^>]*>(\d{2}:\d{2}:\d{2})</span>"
)


def _extract_elapsed(html: str) -> str:
    m = _ELAPSED_RE.search(html)
    assert m, f"Elapsed not found in HTML: {html!r}"
    return m.group(1)


def _extract_step_elapsed(html: str, step_id: str) -> str:
    pattern = re.compile(
        rf"Step {re.escape(step_id)}:</span>\s*<span[^>]*>(\d{{2}}:\d{{2}}:\d{{2}})</span>"
    )
    m = pattern.search(html)
    assert m, f"Step {step_id} Elapsed not found in HTML: {html!r}"
    return m.group(1)


# ---------------------------------------------------------------------------
# Workflow Elapsed
# ---------------------------------------------------------------------------


def test_elapsed_continues_before_mark_all_done(qapp, monkeypatch):
    """対照ケース: mark_all_done 未呼び出し時は時間進行で Elapsed が増える。"""
    state = _make_state()

    monkeypatch.setattr(time, "monotonic", lambda: 5.0)
    w = FooterWidget(state)
    assert _extract_elapsed(w._label.text()) == "00:00:05"

    monkeypatch.setattr(time, "monotonic", lambda: 30.0)
    w._update()
    assert _extract_elapsed(w._label.text()) == "00:00:30"


def test_elapsed_freezes_after_mark_all_done(qapp, monkeypatch):
    """主要回帰: 全タスク完了後は時間が進んでも Elapsed がフリーズする。"""
    state = _make_state()

    # t=5.0 でウィジェット構築
    monkeypatch.setattr(time, "monotonic", lambda: 5.0)
    w = FooterWidget(state)
    assert _extract_elapsed(w._label.text()) == "00:00:05"

    # t=10.0 で全タスク完了 (root.finished_at = 10.0 が設定される)
    monkeypatch.setattr(time, "monotonic", lambda: 10.0)
    state.mark_all_done()
    w._update()
    assert _extract_elapsed(w._label.text()) == "00:00:10"

    # 仮想時間が進んでも完了時刻で固定される
    monkeypatch.setattr(time, "monotonic", lambda: 60.0)
    w._update()
    assert _extract_elapsed(w._label.text()) == "00:00:10"

    monkeypatch.setattr(time, "monotonic", lambda: 3600.0)
    w._update()
    assert _extract_elapsed(w._label.text()) == "00:00:10"


def test_elapsed_freezes_after_mark_aborted(qapp, monkeypatch):
    """abort 経路でも Elapsed がフリーズする (mark_aborted は all_done=True を立てる)。"""
    state = _make_state()

    monkeypatch.setattr(time, "monotonic", lambda: 7.0)
    state.mark_aborted()
    w = FooterWidget(state)
    assert _extract_elapsed(w._label.text()) == "00:00:07"

    monkeypatch.setattr(time, "monotonic", lambda: 100.0)
    w._update()
    assert _extract_elapsed(w._label.text()) == "00:00:07"


def test_elapsed_freezes_with_delayed_update_after_mark_all_done(qapp, monkeypatch):
    """主要回帰 (Major 1 補強): 完了後に時間を進めてから「初回」の _update を
    呼んでも end_time=finished_at で固定されることを確認する。

    本テストが無いと、「完了後の最初の _update 時刻をキャッシュする」誤実装が
    通過してしまう。fix が真に root.finished_at を参照していることを保証する。
    """
    state = _make_state()

    # t=5.0 でウィジェット構築 (Elapsed=00:00:05)
    monkeypatch.setattr(time, "monotonic", lambda: 5.0)
    w = FooterWidget(state)
    assert _extract_elapsed(w._label.text()) == "00:00:05"

    # t=10.0 で全タスク完了 (root.finished_at = 10.0)
    # 注意: ここで _update を呼ばずに時間を進める
    monkeypatch.setattr(time, "monotonic", lambda: 10.0)
    state.mark_all_done()

    # 完了後、最初の描画前に時刻を t=60 に進める
    monkeypatch.setattr(time, "monotonic", lambda: 60.0)
    w._update()
    # 完了時刻 (10.0 - 0.0 = 10s) で固定されるべき
    assert _extract_elapsed(w._label.text()) == "00:00:10"


def test_elapsed_continues_when_all_done_without_root_finished_at(qapp, monkeypatch):
    """実装挙動の明示的 documentation テスト (回帰防止対象ではない)。

    異常経路: mark_all_done() を経由せず ``state.all_done=True`` を手動で
    立てた場合、``root.finished_at`` は None のままなので、修正後実装は
    安全側として ``now`` にフォールバックし、フリーズしない。

    本テストは「将来、`all_done=True` で root.finished_at 欠落時に
    安全側で止める」改善を入れる際にこのテストを更新する必要があることを
    明示するための仕様固定であり、ユーザー可視のバグ回帰を捕捉する目的では
    ない。
    """
    state = _make_state()
    state.all_done = True  # mark_all_done を経由しない異常経路
    # root.finished_at は None のまま

    monkeypatch.setattr(time, "monotonic", lambda: 10.0)
    w = FooterWidget(state)
    assert _extract_elapsed(w._label.text()) == "00:00:10"

    monkeypatch.setattr(time, "monotonic", lambda: 30.0)
    w._update()
    assert _extract_elapsed(w._label.text()) == "00:00:30"


# ---------------------------------------------------------------------------
# Step Elapsed (CRITICAL Major 2 回帰防止)
# ---------------------------------------------------------------------------


def test_step_elapsed_freezes_after_step_done(qapp, monkeypatch):
    """主要回帰 (Major 2): 通常経路 set_step_status('done') により
    SimpleTaskNode.finished_at のみが設定されるケースで Step Elapsed が
    フリーズすることを確認する。

    set_step_status は StepView.finished_at を更新せず task_tree のノード
    だけを更新する。修正後の _update は task_tree.get(step_id).finished_at
    を優先参照する。
    """
    state = _make_state()
    state.steps.append(StepView(id="step-1", title="test step"))

    # t=10.0 でステップ開始 (started_at = 10.0 になる)
    monkeypatch.setattr(time, "monotonic", lambda: 10.0)
    state.set_step_status("step-1", "running")

    # t=11.0 でウィジェット構築 (Step Elapsed=00:00:01)
    monkeypatch.setattr(time, "monotonic", lambda: 11.0)
    w = FooterWidget(state)
    assert _extract_step_elapsed(w._label.text(), "step-1") == "00:00:01"

    # t=15.0 でステップ完了 (task_tree node.finished_at = 15.0)
    monkeypatch.setattr(time, "monotonic", lambda: 15.0)
    state.set_step_status("step-1", "done")
    w._update()
    assert _extract_step_elapsed(w._label.text(), "step-1") == "00:00:05"

    # 検証要点: StepView.finished_at は未設定だが、task_tree 経由で
    # finished_at を参照しているためフリーズが効く。
    sv = state.steps[0]
    assert sv.finished_at is None, (
        "set_step_status は StepView.finished_at を更新しない仕様。"
        " task_tree 経路でフリーズしている事を確認する。"
    )
    node = state.task_tree.get("step-1")
    assert node is not None and node.finished_at == 15.0

    # 時間が進んでも Step Elapsed が固定される
    monkeypatch.setattr(time, "monotonic", lambda: 100.0)
    w._update()
    assert _extract_step_elapsed(w._label.text(), "step-1") == "00:00:05"

    monkeypatch.setattr(time, "monotonic", lambda: 3600.0)
    w._update()
    assert _extract_step_elapsed(w._label.text(), "step-1") == "00:00:05"


def test_step_elapsed_continues_when_running(qapp, monkeypatch):
    """対照ケース: ステップ実行中 (done 前) は Step Elapsed が増える。"""
    state = _make_state()
    state.steps.append(StepView(id="step-1", title="test step"))

    monkeypatch.setattr(time, "monotonic", lambda: 10.0)
    state.set_step_status("step-1", "running")

    monkeypatch.setattr(time, "monotonic", lambda: 12.0)
    w = FooterWidget(state)
    assert _extract_step_elapsed(w._label.text(), "step-1") == "00:00:02"

    monkeypatch.setattr(time, "monotonic", lambda: 40.0)
    w._update()
    assert _extract_step_elapsed(w._label.text(), "step-1") == "00:00:30"


def test_step_elapsed_freezes_with_delayed_update_after_step_done(qapp, monkeypatch):
    """主要回帰 (Major 1 補強): Step 完了後に時間を進めてから「初回」の
    _update を呼んでも node.finished_at で固定されることを確認する。
    """
    state = _make_state()
    state.steps.append(StepView(id="step-1", title="test step"))

    # t=10.0 で開始
    monkeypatch.setattr(time, "monotonic", lambda: 10.0)
    state.set_step_status("step-1", "running")

    # t=12.0 でウィジェット構築 (Step=00:00:02)
    monkeypatch.setattr(time, "monotonic", lambda: 12.0)
    w = FooterWidget(state)
    assert _extract_step_elapsed(w._label.text(), "step-1") == "00:00:02"

    # t=15.0 で完了 (node.finished_at = 15.0)
    # 注意: ここで _update を呼ばずに時間を進める
    monkeypatch.setattr(time, "monotonic", lambda: 15.0)
    state.set_step_status("step-1", "done")

    # 完了後、最初の描画前に時刻を t=100 に進める
    monkeypatch.setattr(time, "monotonic", lambda: 100.0)
    w._update()
    # 完了時刻 (15 - 10 = 5s) で固定されるべき
    assert _extract_step_elapsed(w._label.text(), "step-1") == "00:00:05"
