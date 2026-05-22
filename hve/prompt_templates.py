"""hve.prompt_templates — 9 区分共通テンプレートビルダ

R3 タスク（`work/Issue-orchestration-refactor/remaining/R03/`）の R3.2 で導入。
`hve/prompts.py` の 18 PROMPT 定数が共有する **再利用可能なテキストブロック** を
9 区分のビルダ関数として提供する。

設計方針:
- f-string ベースの **ビルダ関数**（外部依存なし、`{var}` 形式互換）
- 各関数は固定の Boilerplate を返す（PROMPT 固有の本文は caller 側で連結）
- R3.1 で承認済みの 9 区分定義に準拠

9 区分:
  1. system_role         — システムロール / ペルソナ宣言
  2. input_files         — 入力ファイル一覧と必読/推奨の判別
  3. task_scope          — タスクスコープ解析
  4. clarification       — 不明点質問票
  5. planning            — 計画立案（DAG / 分割判定）
  6. implementation      — 実装規約（捏造禁止・最小差分）
  7. verification        — 検証要件（検証マーカー必須）
  8. completion_report   — 完了報告フォーマット
  9. error_recovery      — エラー時のリカバリパターン

呼び出し例:
    from hve.prompt_templates import build_system_role, build_verification
    prompt = (
        build_system_role(role="敵対的レビュアー", expertise="ソフトウェア品質保証")
        + "\\n\\n"
        + ...
        + build_verification()
    )
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# 1. system_role
# ---------------------------------------------------------------------------
def build_system_role(role: str, expertise: str = "") -> str:
    """システムロール / ペルソナ宣言ブロックを生成する。

    Args:
        role: 演じる役割（例: "敵対的レビュアー", "KnowledgeManager"）
        expertise: 専門領域（任意）

    Returns:
        ロール宣言テキスト（末尾改行なし）
    """
    lines = [f"あなたは今から **{role}** として振る舞ってください。"]
    if expertise:
        lines.append(f"専門領域: {expertise}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 2. input_files
# ---------------------------------------------------------------------------
def build_input_files(required_files: list[str] | None = None,
                      recommended_files: list[str] | None = None) -> str:
    """入力ファイル一覧ブロックを生成する。"""
    required_files = required_files or []
    recommended_files = recommended_files or []
    lines = ["## 入力ファイル"]
    if required_files:
        lines.append("### 必読")
        lines.extend(f"- {p}" for p in required_files)
    if recommended_files:
        lines.append("### 推奨")
        lines.extend(f"- {p}" for p in recommended_files)
    if not required_files and not recommended_files:
        lines.append("（入力ファイル指定なし）")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 3. task_scope
# ---------------------------------------------------------------------------
def build_task_scope(scope_source: str = "Issue body / CLI メタ",
                     scope_format: str = "Markdown + HTML コメント") -> str:
    """タスクスコープ解析ブロックを生成する。"""
    return (
        "## タスクスコープ\n"
        f"- 取得元: {scope_source}\n"
        f"- 形式: {scope_format}\n"
        "- HTML コメント（`<!-- key: value -->`）からメタデータを抽出し、本文の指示と整合させること"
    )


# ---------------------------------------------------------------------------
# 4. clarification
# ---------------------------------------------------------------------------
def build_clarification(question_categories: list[str] | None = None) -> str:
    """不明点質問票ブロックを生成する。"""
    question_categories = question_categories or [
        "目的・スコープ", "技術選定", "非機能要件", "受け入れ条件",
    ]
    lines = [
        "## 不明点の確認方針",
        "- 質問なしで進められる場合は質問しない（推論で進めて TBD 明記）",
        "- 必要な質問は重要度（最重要/高/中/低）付きで過不足なく行う",
        "- 質問カテゴリ:",
    ]
    lines.extend(f"  - {c}" for c in question_categories)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 5. planning
# ---------------------------------------------------------------------------
def build_planning(split_criteria: str = "task_scope=multi or context_size=large") -> str:
    """計画立案ブロックを生成する。"""
    return (
        "## 計画立案\n"
        "- タスクを DAG として分解し、`plan.md` + `subissues.md` を作成する\n"
        f"- 分割判定基準: {split_criteria}\n"
        "- plan.md 冒頭 5 行にメタデータ（task_scope / context_size / split_decision / "
        "subissues_count / implementation_files）を必須記載"
    )


# ---------------------------------------------------------------------------
# 6. implementation
# ---------------------------------------------------------------------------
def build_implementation(forbidden_actions: list[str] | None = None) -> str:
    """実装規約ブロックを生成する。"""
    forbidden_actions = forbidden_actions or [
        "捏造（ID/URL/固有名/数値/事実を根拠なく作成）",
        "無関係な整形・一括リファクタ・不要な依存追加",
        "秘密情報（鍵・トークン・個人情報・内部 URL）の追加・出力",
        "ルート README.md の作成・変更",
        "original-docs/ 配下への書き込み（読み取り専用）",
    ]
    lines = [
        "## 実装規約",
        "- 変更は最小差分で行う",
        "- work/ および qa/ への書き込みは「削除→新規作成」ルールに従う",
        "- 不明点は `TBD` または `TBD（推論: {根拠}）` と明記する",
        "- 禁止事項:",
    ]
    lines.extend(f"  - {a}" for a in forbidden_actions)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 7. verification
# ---------------------------------------------------------------------------
def build_verification(verification_marker: str = "<!-- validation-confirmed -->",
                       test_commands: list[str] | None = None) -> str:
    """検証要件ブロックを生成する。"""
    test_commands = test_commands or [
        "pytest（該当テスト）",
        "ruff（lint）",
        "ビルド（該当言語）",
    ]
    lines = [
        "## 検証要件",
        "- 最低 1 つの検証を実施する（テスト/ビルド/静的解析）",
        f"- 完了報告に検証マーカー `{verification_marker}` を記載する",
        "- 検証が困難な場合は「検証: 該当なし（理由: ...、代替: ...）」と記載",
        "- 候補コマンド:",
    ]
    lines.extend(f"  - {c}" for c in test_commands)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 8. completion_report
# ---------------------------------------------------------------------------
def build_completion_report(required_sections: list[str] | None = None) -> str:
    """完了報告フォーマットブロックを生成する。"""
    required_sections = required_sections or [
        "目的", "変更点", "影響範囲", "検証結果", "既知の制約", "次にやるサブタスク",
    ]
    lines = [
        "## 完了報告フォーマット",
        "- 出力先: PR body（GitHub Issue 起点）または `work/Issue-<識別子>/completion-report.md`（CLI 起点）",
        "- 必須セクション:",
    ]
    lines.extend(f"  - {s}" for s in required_sections)
    lines.append("- 元タスク参照を必ず記載（`Fixes #N` / `<!-- parent-task: ... -->`）")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 9. error_recovery
# ---------------------------------------------------------------------------
def build_error_recovery(recovery_strategies: list[str] | None = None) -> str:
    """エラー時のリカバリパターンブロックを生成する。"""
    recovery_strategies = recovery_strategies or [
        "原因の特定（エラーメッセージ・スタックトレース・直前の変更）",
        "影響範囲の評価（テスト失敗範囲・関連ファイル）",
        "修正の最小差分実施 + 再検証",
    ]
    lines = [
        "## エラー時のリカバリ",
        "- 同じアプローチで再試行せず、原因を診断してから修正する",
        "- 書き込み失敗時: read で空でないことを確認、空なら小チャンク再試行（最大 3 回）",
        "- リカバリ手順:",
    ]
    lines.extend(f"  - {s}" for s in recovery_strategies)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 公開 API
# ---------------------------------------------------------------------------
__all__ = [
    "build_system_role",
    "build_input_files",
    "build_task_scope",
    "build_clarification",
    "build_planning",
    "build_implementation",
    "build_verification",
    "build_completion_report",
    "build_error_recovery",
]
