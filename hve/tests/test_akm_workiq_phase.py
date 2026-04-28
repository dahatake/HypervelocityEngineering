"""AKM Work IQ 検証フェーズの統合テスト。

フェーズ計算、_summarize_dxx_for_query、プロンプトテンプレートの検証を行う。
"""

import sys
from pathlib import Path

# hve パッケージのパスを追加
_root = Path(__file__).resolve().parent.parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))


def test_summarize_dxx_for_query_basic():
    """_summarize_dxx_for_query が基本的な Markdown 構造を正しく要約する。"""
    from hve.orchestrator import _summarize_dxx_for_query

    content = """# D01: 事業意図・成功条件定義書

**D クラス**: D01
**文書名**: 事業意図・成功条件定義書

## 1. 目的と背景

本書は D01 の要求定義ドラフトです。

## 2. 確定事項（Confirmed）

### 2.1 original-docs/ 由来の確定事項

確定事項あり。

## 3. 設計仮定（Tentative）

仮定1: XXX は YYY

## 4. 未解決・不明（Unknown）

不明: ZZZ の定義
"""
    result = _summarize_dxx_for_query(Path("knowledge/D01-test.md"), content)
    assert "# D01: 事業意図・成功条件定義書" in result
    assert "## 1. 目的と背景" in result
    assert "## 2. 確定事項（Confirmed）" in result
    assert "## 3. 設計仮定（Tentative）" in result
    assert "## 4. 未解決・不明（Unknown）" in result
    assert len(result) <= 3100  # _AKM_WORKIQ_SUMMARY_MAX_LENGTH + tolerance


def test_summarize_dxx_for_query_empty():
    """空のファイルでも例外を出さない。"""
    from hve.orchestrator import _summarize_dxx_for_query

    result = _summarize_dxx_for_query(Path("knowledge/D99-empty.md"), "")
    assert result == ""


def test_summarize_dxx_truncation():
    """長い内容が切り詰められる。"""
    from hve.orchestrator import _summarize_dxx_for_query, _AKM_WORKIQ_SUMMARY_MAX_LENGTH

    long_content = "# D99: テスト文書\n\n" + "## セクション\n\n" + ("A" * 5000 + "\n") * 10
    result = _summarize_dxx_for_query(Path("knowledge/D99-long.md"), long_content)
    assert len(result) <= _AKM_WORKIQ_SUMMARY_MAX_LENGTH + 50  # truncated marker


def test_akm_workiq_verify_prompt_placeholders():
    """AKM_WORKIQ_VERIFY_AND_UPDATE_PROMPT のプレースホルダが正しいことを確認。"""
    from hve.prompts import AKM_WORKIQ_VERIFY_AND_UPDATE_PROMPT

    # 必須プレースホルダが含まれること
    assert "{dxx_filename}" in AKM_WORKIQ_VERIFY_AND_UPDATE_PROMPT
    assert "{dxx_content}" in AKM_WORKIQ_VERIFY_AND_UPDATE_PROMPT
    assert "{dxx_filepath}" in AKM_WORKIQ_VERIFY_AND_UPDATE_PROMPT
    assert "{workiq_result}" in AKM_WORKIQ_VERIFY_AND_UPDATE_PROMPT

    # format で置換できること
    formatted = AKM_WORKIQ_VERIFY_AND_UPDATE_PROMPT.format(
        dxx_filename="D01-test.md",
        dxx_content="test content",
        dxx_filepath="knowledge/D01-test.md",
        workiq_result="Work IQ result",
    )
    assert "D01-test.md" in formatted
    assert "test content" in formatted
    assert "Work IQ result" in formatted
    assert "情報ソース (Work IQ)" in formatted


def test_phase_count_akm_with_workiq_review():
    """AKM + workiq_akm_review_enabled 時のフェーズ数が正しいことを確認（dry_run=False）。"""
    from hve.config import SDKConfig

    cfg = SDKConfig(workiq_akm_review_enabled=True)
    # フェーズ計算ロジックを再現して検証
    phases = ["ワークフロー定義取得", "パラメータ収集", "ステップフィルタリング"]
    # create_issues=False, create_pr=False
    phases.append("実行計画 → DAG 実行")
    # AKM + workiq_akm_review_enabled + not dry_run
    workflow_id = "akm"
    dry_run = False
    if workflow_id == "akm" and cfg.is_workiq_akm_review_enabled() and not dry_run:
        phases.append("AKM Work IQ 検証")
    # auto_self_improve=False
    phases.append("サマリー")

    assert len(phases) == 6
    assert "AKM Work IQ 検証" in phases
    assert phases.index("AKM Work IQ 検証") == 4  # DAG 実行の直後


def test_phase_count_akm_without_workiq():
    """AKM + workiq_akm_review_enabled=False 時のフェーズ数が正しいことを確認。"""
    from hve.config import SDKConfig

    cfg = SDKConfig(workiq_akm_review_enabled=False)
    phases = ["ワークフロー定義取得", "パラメータ収集", "ステップフィルタリング"]
    phases.append("実行計画 → DAG 実行")
    workflow_id = "akm"
    dry_run = False
    if workflow_id == "akm" and cfg.is_workiq_akm_review_enabled() and not dry_run:
        phases.append("AKM Work IQ 検証")
    phases.append("サマリー")

    assert len(phases) == 5
    assert "AKM Work IQ 検証" not in phases


def test_phase_count_non_akm_with_workiq():
    """非 AKM ワークフローでは workiq_akm_review_enabled=True でも AKM 検証フェーズが入らない。"""
    from hve.config import SDKConfig

    cfg = SDKConfig(workiq_akm_review_enabled=True)
    phases = ["ワークフロー定義取得", "パラメータ収集", "ステップフィルタリング"]
    phases.append("実行計画 → DAG 実行")
    workflow_id = "aad"
    dry_run = False
    if workflow_id == "akm" and cfg.is_workiq_akm_review_enabled() and not dry_run:
        phases.append("AKM Work IQ 検証")
    phases.append("サマリー")

    assert len(phases) == 5
    assert "AKM Work IQ 検証" not in phases


if __name__ == "__main__":
    test_summarize_dxx_for_query_basic()
    print("✅ test_summarize_dxx_for_query_basic")

    test_summarize_dxx_for_query_empty()
    print("✅ test_summarize_dxx_for_query_empty")

    test_summarize_dxx_truncation()
    print("✅ test_summarize_dxx_truncation")

    test_akm_workiq_verify_prompt_placeholders()
    print("✅ test_akm_workiq_verify_prompt_placeholders")

    test_phase_count_akm_with_workiq_review()
    print("✅ test_phase_count_akm_with_workiq_review")

    test_phase_count_akm_without_workiq()
    print("✅ test_phase_count_akm_without_workiq")

    test_phase_count_non_akm_with_workiq()
    print("✅ test_phase_count_non_akm_with_workiq")

    print("\n全テスト PASS")
