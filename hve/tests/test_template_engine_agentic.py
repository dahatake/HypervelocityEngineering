"""test_template_engine_agentic.py — Agentic Retrieval 質問項目の同期検証テスト（Phase 7）

Issue Form YAML と template_engine.py の _AGENTIC_RETRIEVAL_QUESTIONS 定数の整合性、
normalize_agentic_retrieval_answers の正規化挙動、および format_agentic_retrieval_block の
出力構造を検証する。

NOTE: Q1=no/yes/auto の基本正規化テストは
      test_template_engine.py::TestAgenticRetrievalConstants で実施済み。
      本ファイルは YAML↔Python 定数同期・ format_agentic_retrieval_block・未カバー補完に集中する。
"""

from __future__ import annotations

from pathlib import Path

import yaml  # PyYAML は CI (test-hve-python.yml) で必須インストール済み

_REPO_ROOT = Path(__file__).resolve().parents[2]
_TEMPLATE_DIR = _REPO_ROOT / ".github" / "ISSUE_TEMPLATE"


# ---------------------------------------------------------------------------
# ユーティリティ
# ---------------------------------------------------------------------------


def _load_issue_form_yaml(filename: str) -> dict:
    """Issue Template YAML を読み込む。"""
    return yaml.safe_load((_TEMPLATE_DIR / filename).read_text(encoding="utf-8"))


def _extract_agentic_fields(yaml_data: dict) -> dict[str, dict]:
    """YAML body から Agentic Retrieval 関連フィールドを id → body アイテムの辞書で返す。"""
    from hve.template_engine import _AGENTIC_RETRIEVAL_QUESTIONS

    agentic_ids = set(_AGENTIC_RETRIEVAL_QUESTIONS.keys())
    result = {}
    for item in yaml_data.get("body", []):
        item_id = item.get("id")
        if item_id in agentic_ids:
            result[item_id] = item
    return result


# ---------------------------------------------------------------------------
# 1-1. Issue Form YAML と _AGENTIC_RETRIEVAL_QUESTIONS の同期検証
# ---------------------------------------------------------------------------


class TestIssueFormYamlSync:
    """Issue Form YAML と _AGENTIC_RETRIEVAL_QUESTIONS 定数のフィールド同期を検証する。"""

    def test_aad_web_yaml_has_exactly_q1_and_q3(self):
        """web-app-design.yml の Agentic Retrieval フィールドが Q1・Q3 の 2 件だけであること。"""
        yaml_data = _load_issue_form_yaml("web-app-design.yml")
        fields = _extract_agentic_fields(yaml_data)
        assert set(fields.keys()) == {"enable_agentic_retrieval", "foundry_mcp_integration"}

    def test_asdw_web_yaml_has_all_six_questions(self):
        """web-app-dev.yml の Agentic Retrieval フィールドが Q1〜Q6 の 6 件すべてであること。"""
        yaml_data = _load_issue_form_yaml("web-app-dev.yml")
        fields = _extract_agentic_fields(yaml_data)
        expected_ids = {
            "enable_agentic_retrieval",
            "agentic_data_source_modes",
            "foundry_mcp_integration",
            "agentic_data_sources_hint",
            "agentic_existing_design_diff_only",
            "foundry_sku_fallback_policy",
        }
        assert set(fields.keys()) == expected_ids

    def test_aad_web_enable_agentic_retrieval_label_matches(self):
        """web-app-design.yml の enable_agentic_retrieval ラベルが定数と一致すること。"""
        from hve.template_engine import _AGENTIC_RETRIEVAL_QUESTIONS

        yaml_data = _load_issue_form_yaml("web-app-design.yml")
        fields = _extract_agentic_fields(yaml_data)
        expected_label = _AGENTIC_RETRIEVAL_QUESTIONS["enable_agentic_retrieval"]["label"]
        actual_label = fields["enable_agentic_retrieval"]["attributes"]["label"]
        assert actual_label == expected_label

    def test_aad_web_foundry_mcp_integration_label_matches(self):
        """web-app-design.yml の foundry_mcp_integration ラベルが定数と一致すること。"""
        from hve.template_engine import _AGENTIC_RETRIEVAL_QUESTIONS

        yaml_data = _load_issue_form_yaml("web-app-design.yml")
        fields = _extract_agentic_fields(yaml_data)
        expected_label = _AGENTIC_RETRIEVAL_QUESTIONS["foundry_mcp_integration"]["label"]
        actual_label = fields["foundry_mcp_integration"]["attributes"]["label"]
        assert actual_label == expected_label

    def test_asdw_web_enable_agentic_retrieval_label_matches(self):
        """web-app-dev.yml の enable_agentic_retrieval ラベルが定数と一致すること。"""
        from hve.template_engine import _AGENTIC_RETRIEVAL_QUESTIONS

        yaml_data = _load_issue_form_yaml("web-app-dev.yml")
        fields = _extract_agentic_fields(yaml_data)
        expected_label = _AGENTIC_RETRIEVAL_QUESTIONS["enable_agentic_retrieval"]["label"]
        actual_label = fields["enable_agentic_retrieval"]["attributes"]["label"]
        assert actual_label == expected_label

    def test_asdw_web_enable_agentic_retrieval_options_match(self):
        """web-app-dev.yml の enable_agentic_retrieval options が定数と一致すること。"""
        from hve.template_engine import _AGENTIC_RETRIEVAL_QUESTIONS

        yaml_data = _load_issue_form_yaml("web-app-dev.yml")
        fields = _extract_agentic_fields(yaml_data)
        expected_options = _AGENTIC_RETRIEVAL_QUESTIONS["enable_agentic_retrieval"]["options"]
        # YAML パーサーが数値や boolean を返す可能性があるため明示的に文字列化して比較する
        actual_options = [str(o) for o in fields["enable_agentic_retrieval"]["attributes"]["options"]]
        assert actual_options == expected_options

    def test_asdw_web_enable_agentic_retrieval_default_matches(self):
        """web-app-dev.yml の enable_agentic_retrieval default が定数と一致すること。"""
        from hve.template_engine import _AGENTIC_RETRIEVAL_QUESTIONS

        yaml_data = _load_issue_form_yaml("web-app-dev.yml")
        fields = _extract_agentic_fields(yaml_data)
        expected_default = _AGENTIC_RETRIEVAL_QUESTIONS["enable_agentic_retrieval"]["default"]
        actual_default = fields["enable_agentic_retrieval"]["attributes"].get("default")
        assert actual_default == expected_default

    def test_asdw_web_foundry_mcp_integration_label_matches(self):
        """web-app-dev.yml の foundry_mcp_integration ラベルが定数と一致すること。"""
        from hve.template_engine import _AGENTIC_RETRIEVAL_QUESTIONS

        yaml_data = _load_issue_form_yaml("web-app-dev.yml")
        fields = _extract_agentic_fields(yaml_data)
        expected_label = _AGENTIC_RETRIEVAL_QUESTIONS["foundry_mcp_integration"]["label"]
        actual_label = fields["foundry_mcp_integration"]["attributes"]["label"]
        assert actual_label == expected_label

    def test_asdw_web_foundry_mcp_integration_options_match(self):
        """web-app-dev.yml の foundry_mcp_integration options が定数と一致すること。"""
        from hve.template_engine import _AGENTIC_RETRIEVAL_QUESTIONS

        yaml_data = _load_issue_form_yaml("web-app-dev.yml")
        fields = _extract_agentic_fields(yaml_data)
        expected_options = _AGENTIC_RETRIEVAL_QUESTIONS["foundry_mcp_integration"]["options"]
        # YAML パーサーが数値や boolean を返す可能性があるため明示的に文字列化して比較する
        actual_options = [str(o) for o in fields["foundry_mcp_integration"]["attributes"]["options"]]
        assert actual_options == expected_options

    def test_asdw_web_foundry_sku_fallback_label_matches(self):
        """web-app-dev.yml の foundry_sku_fallback_policy ラベルが定数と一致すること。"""
        from hve.template_engine import _AGENTIC_RETRIEVAL_QUESTIONS

        yaml_data = _load_issue_form_yaml("web-app-dev.yml")
        fields = _extract_agentic_fields(yaml_data)
        expected_label = _AGENTIC_RETRIEVAL_QUESTIONS["foundry_sku_fallback_policy"]["label"]
        actual_label = fields["foundry_sku_fallback_policy"]["attributes"]["label"]
        assert actual_label == expected_label

    def test_asdw_web_foundry_sku_fallback_options_match(self):
        """web-app-dev.yml の foundry_sku_fallback_policy options が定数と一致すること。"""
        from hve.template_engine import _AGENTIC_RETRIEVAL_QUESTIONS

        yaml_data = _load_issue_form_yaml("web-app-dev.yml")
        fields = _extract_agentic_fields(yaml_data)
        expected_options = _AGENTIC_RETRIEVAL_QUESTIONS["foundry_sku_fallback_policy"]["options"]
        # YAML パーサーが数値や boolean を返す可能性があるため明示的に文字列化して比較する
        actual_options = [str(o) for o in fields["foundry_sku_fallback_policy"]["attributes"]["options"]]
        assert actual_options == expected_options

    def test_asdw_web_all_agentic_ids_in_expected_set(self):
        """web-app-dev.yml のすべての Agentic Retrieval id が期待値セット内であること。"""
        expected_ids = {
            "enable_agentic_retrieval",
            "agentic_data_source_modes",
            "foundry_mcp_integration",
            "agentic_data_sources_hint",
            "agentic_existing_design_diff_only",
            "foundry_sku_fallback_policy",
        }
        yaml_data = _load_issue_form_yaml("web-app-dev.yml")
        fields = _extract_agentic_fields(yaml_data)
        for field_id in fields:
            assert field_id in expected_ids, \
                f"web-app-dev.yml に未知の Agentic Retrieval id '{field_id}' が存在します"


# ---------------------------------------------------------------------------
# 1-2. normalize_agentic_retrieval_answers の補完検証
# ---------------------------------------------------------------------------


class TestNormalizeAgenticRetrievalAnswers:
    """normalize_agentic_retrieval_answers の補完テスト。

    NOTE: Q1=no/yes/auto/しない/する/自動判定に従う の基本検証は
          test_template_engine.py::TestAgenticRetrievalConstants で実施済み。
          本クラスは未カバー観点を担当する。
    """

    def test_agentic_data_source_modes_default_is_indexer_in_config(self):
        """SDKConfig の agentic_data_source_modes デフォルトが ["indexer"] であること（Phase 2 仕様）。"""
        from hve.config import SDKConfig

        cfg = SDKConfig()
        assert cfg.agentic_data_source_modes == ["indexer"]

    def test_normalize_does_not_mutate_original(self):
        """normalize_agentic_retrieval_answers は入力辞書を変更しないこと。"""
        from hve.template_engine import normalize_agentic_retrieval_answers

        original = {
            "enable_agentic_retrieval": "no",
            "foundry_mcp_integration": "する",
        }
        original_copy = dict(original)
        normalize_agentic_retrieval_answers(original)
        assert original == original_copy

    def test_normalize_no_leaves_data_source_modes_unchanged(self):
        """Q1=no のとき、agentic_data_source_modes は変更されないこと。"""
        from hve.template_engine import normalize_agentic_retrieval_answers

        answers = {
            "enable_agentic_retrieval": "no",
            "agentic_data_source_modes": ["Indexer (Pull)", "Push API"],
        }
        result = normalize_agentic_retrieval_answers(answers)
        assert result["agentic_data_source_modes"] == ["Indexer (Pull)", "Push API"]

    def test_normalize_auto_leaves_data_source_modes_unchanged(self):
        """Q1=auto のとき、agentic_data_source_modes は変更されないこと。"""
        from hve.template_engine import normalize_agentic_retrieval_answers

        answers = {
            "enable_agentic_retrieval": "auto",
            "agentic_data_source_modes": ["Push API"],
        }
        result = normalize_agentic_retrieval_answers(answers)
        assert result["agentic_data_source_modes"] == ["Push API"]

    def test_normalize_empty_dict_does_not_raise(self):
        """空の辞書を渡してもエラーにならないこと。"""
        from hve.template_engine import normalize_agentic_retrieval_answers

        result = normalize_agentic_retrieval_answers({})
        assert result == {}

    def test_normalize_extra_keys_preserved(self):
        """normalize が知らないキーはそのまま保持されること。"""
        from hve.template_engine import normalize_agentic_retrieval_answers

        answers = {
            "enable_agentic_retrieval": "no",
            "unrelated_key": "some_value",
        }
        result = normalize_agentic_retrieval_answers(answers)
        assert result["unrelated_key"] == "some_value"


# ---------------------------------------------------------------------------
# 1-3. format_agentic_retrieval_block の基本検証
# ---------------------------------------------------------------------------


class TestFormatAgenticRetrievalBlock:
    """format_agentic_retrieval_block の出力構造を検証する。"""

    def test_aad_web_block_contains_q1_label(self):
        """AAD-WEB ブロックには Q1（enable_agentic_retrieval）の label が含まれること。"""
        from hve.template_engine import (
            _AGENTIC_RETRIEVAL_QUESTIONS,
            format_agentic_retrieval_block,
        )

        block = format_agentic_retrieval_block("aad-web")
        assert _AGENTIC_RETRIEVAL_QUESTIONS["enable_agentic_retrieval"]["label"] in block

    def test_aad_web_block_contains_q3_label(self):
        """AAD-WEB ブロックには Q3（foundry_mcp_integration）の label が含まれること。"""
        from hve.template_engine import (
            _AGENTIC_RETRIEVAL_QUESTIONS,
            format_agentic_retrieval_block,
        )

        block = format_agentic_retrieval_block("aad-web")
        assert _AGENTIC_RETRIEVAL_QUESTIONS["foundry_mcp_integration"]["label"] in block

    def test_aad_web_block_does_not_contain_asdw_only_labels(self):
        """AAD-WEB ブロックには ASDW-WEB 専用質問の label が含まれないこと。"""
        from hve.template_engine import (
            _AGENTIC_RETRIEVAL_QUESTIONS,
            format_agentic_retrieval_block,
        )

        block = format_agentic_retrieval_block("aad-web")
        asdw_only_keys = [
            "agentic_data_source_modes",
            "agentic_data_sources_hint",
            "agentic_existing_design_diff_only",
            "foundry_sku_fallback_policy",
        ]
        for key in asdw_only_keys:
            label = _AGENTIC_RETRIEVAL_QUESTIONS[key]["label"]
            assert label not in block, \
                f"AAD-WEB ブロックに ASDW-WEB 専用ラベル '{label}' が含まれています"

    def test_asdw_web_block_contains_all_six_labels(self):
        """ASDW-WEB ブロックには Q1〜Q6 全ての label が含まれること。"""
        from hve.template_engine import (
            _AGENTIC_RETRIEVAL_QUESTIONS,
            format_agentic_retrieval_block,
        )

        block = format_agentic_retrieval_block("asdw-web")
        for key, q in _AGENTIC_RETRIEVAL_QUESTIONS.items():
            assert q["label"] in block, \
                f"ASDW-WEB ブロックに '{key}' の label '{q['label']}' が含まれていません"

    def test_non_target_workflow_aas_returns_empty(self):
        """Agentic Retrieval 非対象の aas では空文字列が返ること。"""
        from hve.template_engine import format_agentic_retrieval_block

        assert format_agentic_retrieval_block("aas") == ""

    def test_non_target_workflow_abd_returns_empty(self):
        """Agentic Retrieval 非対象の abd では空文字列が返ること。"""
        from hve.template_engine import format_agentic_retrieval_block

        assert format_agentic_retrieval_block("abd") == ""

    def test_alias_aad_same_as_aad_web(self):
        """後方互換エイリアス 'aad' と 'aad-web' の出力が同一であること。"""
        from hve.template_engine import format_agentic_retrieval_block

        assert format_agentic_retrieval_block("aad") == format_agentic_retrieval_block("aad-web")

    def test_alias_asdw_same_as_asdw_web(self):
        """後方互換エイリアス 'asdw' と 'asdw-web' の出力が同一であること。"""
        from hve.template_engine import format_agentic_retrieval_block

        assert format_agentic_retrieval_block("asdw") == format_agentic_retrieval_block("asdw-web")

    def test_unknown_workflow_returns_empty(self):
        """未知のワークフロー ID では空文字列が返ること。"""
        from hve.template_engine import format_agentic_retrieval_block

        assert format_agentic_retrieval_block("unknown-workflow") == ""

    def test_aad_web_block_is_non_empty(self):
        """AAD-WEB ブロックが空でないこと。"""
        from hve.template_engine import format_agentic_retrieval_block

        assert len(format_agentic_retrieval_block("aad-web")) > 0

    def test_asdw_web_block_longer_than_aad_web_block(self):
        """ASDW-WEB ブロックは AAD-WEB ブロックより長いこと（より多くの質問を含む）。"""
        from hve.template_engine import format_agentic_retrieval_block

        aad_block = format_agentic_retrieval_block("aad-web")
        asdw_block = format_agentic_retrieval_block("asdw-web")
        assert len(asdw_block) > len(aad_block)
