"""get_parser_input_path / _PARSER_INPUT_PATHS の単体テスト。

T-A1: parser 名 → 主入力ファイルパスのマッピングが、各 parser の実際の
_read_text 呼び出し先（および parse_screen_catalog の glob パターン）と
一致していることを検証する。
"""
from __future__ import annotations

from hve.catalog_parsers import (
    KNOWN_PARSERS,
    _PARSER_INPUT_PATHS,
    get_parser_input_path,
)


def test_get_parser_input_path_returns_expected_paths() -> None:
    """各 parser 名に対し、実装が読み込むファイルパスが返ることを検証。"""
    expected = {
        "app_catalog": "docs/catalog/app-catalog.md",
        "screen_catalog": "docs/catalog/screen-catalog-APP-*.md",
        "service_catalog": "docs/catalog/service-catalog.md",
        "dataflow_catalog": "docs/dataflow/dataflow-app-catalog.md",
        "agent_catalog": "docs/agent/agent-application-definition.md",
        "business_candidate": "docs/company-business-recommendation.md",
        "use_case_skeleton": "docs/catalog/use-case-skeleton.md",
    }
    for name, path in expected.items():
        assert get_parser_input_path(name) == path, (
            f"parser '{name}' の入力パスが期待値と一致しません"
        )


def test_get_parser_input_path_unknown_returns_none() -> None:
    """未登録 parser 名は None を返す。"""
    assert get_parser_input_path("nonexistent_parser") is None
    assert get_parser_input_path("") is None


def test_parser_input_paths_covers_all_known_parsers() -> None:
    """KNOWN_PARSERS と _PARSER_INPUT_PATHS のキー集合が完全一致する。

    新規 parser を _PARSERS に追加した際に _PARSER_INPUT_PATHS への追加を
    忘れることを防ぐ regression テスト。
    """
    assert set(KNOWN_PARSERS) == set(_PARSER_INPUT_PATHS.keys()), (
        "KNOWN_PARSERS と _PARSER_INPUT_PATHS のキーが一致しません: "
        f"差分={set(KNOWN_PARSERS) ^ set(_PARSER_INPUT_PATHS.keys())}"
    )
