"""auto-approve-and-merge workflow の deploy AC gate 契約テスト。"""

from __future__ import annotations

from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[2]
_WORKFLOW = _REPO_ROOT / ".github" / "workflows" / "auto-approve-and-merge.yml"


def _deploy_ac_gate_section() -> str:
    text = _WORKFLOW.read_text(encoding="utf-8")
    start = text.index("      - name: Deploy / AC gate 確認")
    end = text.index("      - name: PR を Approve", start)
    return text[start:end]


def test_deploy_ac_gate_does_not_require_ac13_from_ai_words_only() -> None:
    """SWA UI deploy PR が APP 名などの AI 文脈だけで AC-13 要求されないこと。"""
    section = _deploy_ac_gate_section()

    assert "ac13_required=\"false\"" in section
    assert "create-azure-additional-resources" in section
    assert "deploy-step2-additional-test-spec" in section
    assert "grep -Eiq '(AI|LLM|Foundry|OpenAI|Copilot)'" not in section
    assert "AI/LLM 文脈で `AC-13" not in section


def test_deploy_ac_gate_still_validates_ac13_when_present_or_required() -> None:
    """追加 Azure サービス deploy と明示 AC-13 行の検証は維持する。"""
    section = _deploy_ac_gate_section()

    assert "AC-13" in section
    assert "追加 Azure サービス deploy PR" in section
    assert "elif [ \"${ac13_required}\" = \"true\" ]; then" in section
    assert "^[[:space:]]*\\|[[:space:]]*AC-13" in section
    assert "(✅|N/A|NA|該当なし)" in section


def test_deploy_ac_gate_checks_status_column_not_whole_row() -> None:
    """AC テーブル行の not-green 判定を状態カラム（3列目）に限定すること。

    証跡カラムはスクリプト実出力（例: `FAIL=0`）や設計注記（例: マージ後手動の
    ため未実行）を含むため、whole-row substring 照合だと成功シグナルを誤検出する。
    runner 側 validate_deploy_ac_verification と同じく状態カラムのみで判定する。
    """
    section = _deploy_ac_gate_section()

    # 状態カラム（3列目）を awk で抽出している。
    assert "awk -F'|' '{ print $4 }'" in section
    assert "ac_status_cells=" in section
    # not-green 判定は状態カラムに対して行い、記号系マーカーのみを見る。
    assert (
        "printf '%s' \"${ac_status_cells}\" | grep -Eq 'NEEDS-VERIFICATION|❌|⏳'"
        in section
    )
    # 旧挙動: AC テーブル行全体（証跡含む）への FAIL/未実行 substring 判定は廃止。
    assert "\"${ac_table_rows}\" | grep -Eiq 'NEEDS-VERIFICATION" not in section
    # 必須 AC の ✅ 強制ループは維持（状態カラム化しても ac_table_rows を使う）。
    assert "for required_ac in AC-2 AC-3 AC-6 AC-8 AC-9 AC4B-1" in section


def test_deploy_ac_gate_global_keyword_net_scopes_to_combined_text() -> None:
    """全体キーワード net を PR 本文/コメント（combined_text）に限定すること。

    ac-verification.md（ac_text）はテーブル行チェック（状態カラム＋必須 AC ✅）で
    権威的に検証済み。証跡 prose を naive substring で再走査すると `FAIL=0` や
    「マージ後手動のため未実行」等を誤検出するため、net は combined_text に限定する。
    """
    section = _deploy_ac_gate_section()

    # net は combined_text（PR 本文/コメント）を対象にする。
    assert (
        "printf '%s' \"${combined_text}\" | grep -Eiq "
        "'NEEDS-VERIFICATION|⏳|FAIL|未実行|手動実行が必要|残作業'"
        in section
    )
    # 旧挙動: source_text（ac_text 含む）への FAIL/未実行 net は廃止。
    assert "\"${source_text}\" | grep -Eiq 'NEEDS-VERIFICATION" not in section
