"""hve.gui.i18n 基盤のテスト。

- ``resolve_language()`` の優先順位
- ``install_translator()`` の正常系・異常系
- ``.qm`` ファイルが存在し、ロード可能であること
- 設定ファイルの ``language`` キーが既定値に含まれていること
"""

from __future__ import annotations

import html
import os
import sys
from pathlib import Path
from unittest import mock

import pytest

# QApplication が必要な可能性があるため pytest-qt を使わない簡易テスト構成
pytest.importorskip("PySide6")

from PySide6.QtCore import QCoreApplication

from hve.gui import i18n, settings_store


_I18N_DIR = Path(i18n.__file__).resolve().parent


def _escape(text: str) -> str:
    """`.ts` へ書き出されるのと同じ XML エスケープを施す。"""
    return html.escape(text, quote=False)


# ---------------------------------------------------------------------------
# resolve_language
# ---------------------------------------------------------------------------
class TestResolveLanguage:
    def test_env_var_supersedes_stored(self) -> None:
        with mock.patch.dict(os.environ, {"HVE_GUI_LANG": "en_US"}, clear=False):
            assert i18n.resolve_language("ja_JP") == "en_US"

    def test_env_var_ja_jp(self) -> None:
        with mock.patch.dict(os.environ, {"HVE_GUI_LANG": "ja_JP"}, clear=False):
            assert i18n.resolve_language("en_US") == "ja_JP"

    def test_env_auto_falls_through(self) -> None:
        with mock.patch.dict(os.environ, {"HVE_GUI_LANG": "auto"}, clear=False):
            # auto なので stored 値を採用
            assert i18n.resolve_language("ja_JP") == "ja_JP"

    def test_invalid_env_falls_through_to_stored(self) -> None:
        with mock.patch.dict(os.environ, {"HVE_GUI_LANG": "xx_XX"}, clear=False):
            assert i18n.resolve_language("en_US") == "en_US"

    def test_stored_ja_jp(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            assert i18n.resolve_language("ja_JP") == "ja_JP"

    def test_stored_en_us(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            assert i18n.resolve_language("en_US") == "en_US"

    def test_none_falls_back_to_os_detection(self) -> None:
        # OS 検出結果は環境依存だが、サポート言語のいずれかが返ることを確認
        with mock.patch.dict(os.environ, {}, clear=True):
            result = i18n.resolve_language(None)
            assert result in i18n.SUPPORTED_LANGUAGES

    def test_empty_falls_back_to_os_detection(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            result = i18n.resolve_language("")
            assert result in i18n.SUPPORTED_LANGUAGES

    def test_auto_falls_back_to_os_detection(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            result = i18n.resolve_language("auto")
            assert result in i18n.SUPPORTED_LANGUAGES


# ---------------------------------------------------------------------------
# install_translator
# ---------------------------------------------------------------------------
class TestInstallTranslator:
    @pytest.fixture(autouse=True)
    def _ensure_app(self) -> None:
        # 翻訳 install には QCoreApplication で十分だが、同一 pytest プロセス内の
        # 後続 GUI テスト（QWidget ベース）は QApplication を要求する。ここで
        # 非 GUI の QCoreApplication を先に生成すると "Cannot create a QWidget
        # without QApplication" で後続がクラッシュ/ハングするため、GUI と共存
        # できる QApplication を生成する。
        from PySide6.QtWidgets import QApplication

        self._app = QApplication.instance() or QApplication(sys.argv[:1])

    def test_source_language_returns_true_without_load(self) -> None:
        # ja_JP はソース言語のため .qm ロード不要、True を返す
        assert i18n.install_translator(self._app, "ja_JP") is True

    def test_en_us_loads_qm_if_present(self) -> None:
        qm_path = _I18N_DIR / "hve_gui_en_US.qm"
        if not qm_path.exists():
            pytest.skip(".qm not built; run setup-hve to compile")
        try:
            assert i18n.install_translator(self._app, "en_US") is True
        finally:
            # 後続テスト（例: test_status_banner の "待機" 等 ja_JP 文言検証）への
            # 翻訳汚染を防ぐため、ソース言語 ja_JP へ戻して QTranslator を取り外す。
            # install_translator(app, "ja_JP") は既存 translator を removeTranslator する。
            i18n.install_translator(self._app, "ja_JP")


# ---------------------------------------------------------------------------
# 設定 / アセット
# ---------------------------------------------------------------------------
class TestSettings:
    def test_language_key_in_defaults(self) -> None:
        defaults = settings_store.defaults()
        assert "language" in defaults["options"]
        assert defaults["options"]["language"] == "auto"


class TestAssets:
    def test_translations_pro_exists(self) -> None:
        assert (_I18N_DIR / "translations.pro").exists()

    def test_ts_exists_with_messages(self) -> None:
        ts_path = _I18N_DIR / "hve_gui_en_US.ts"
        assert ts_path.exists()
        content = ts_path.read_text(encoding="utf-8")
        assert '<source>' in content
        assert 'sourcelanguage="ja_JP"' in content or 'language="en_US"' in content

    def test_cq_settings_section_is_translated(self) -> None:
        """FR-GUI-04: Code-Query セクションの文字列が翻訳カタログに載っていること。"""
        sources = (_I18N_DIR / "translations.pro").read_text(encoding="utf-8")
        assert "cq/gui/settings_section.py" in sources

        content = (_I18N_DIR / "hve_gui_en_US.ts").read_text(encoding="utf-8")
        assert '<context>\n    <name>CqIndexSection</name>' in content
        assert "<source>インデックス管理</source>" in content

    def test_gh_login_dialog_is_translated(self) -> None:
        """FR-GUI-09: GitHub CLI ログイン案内の文言が翻訳カタログに載っていること。"""
        sources = (_I18N_DIR / "translations.pro").read_text(encoding="utf-8")
        assert "../gh_login_dialog.py" in sources

        content = (_I18N_DIR / "hve_gui_en_US.ts").read_text(encoding="utf-8")
        assert '<context>\n    <name>GhLoginDialog</name>' in content
        context = content.split("<name>GhLoginDialog</name>", 1)[1].split("</context>", 1)[0]
        assert 'type="unfinished"' not in context

    def test_copilot_chat_panel_is_translated(self) -> None:
        """FR-GUI-10 / FR-GUI-12: Copilot パネルの新 UI 文言が翻訳済みであること。"""
        sources = (_I18N_DIR / "translations.pro").read_text(encoding="utf-8")
        assert "../copilot_chat_panel.py" in sources

        content = (_I18N_DIR / "hve_gui_en_US.ts").read_text(encoding="utf-8")
        assert '<context>\n    <name>CopilotChatPanel</name>' in content
        context = content.split("<name>CopilotChatPanel</name>", 1)[1].split("</context>", 1)[0]
        assert "<source>実行ジョブ</source>" in context
        assert "<source>会話をクリア</source>" in context
        assert "<source>前の送信メッセージへ</source>" in context
        assert "<source>次の送信メッセージへ</source>" in context
        assert 'type="unfinished"' not in context

    def test_job_chat_widgets_are_translated(self) -> None:
        """FR-GUI-18: 会話ビュー / 入力ボックスの文言が翻訳済みであること。"""
        sources = (_I18N_DIR / "translations.pro").read_text(encoding="utf-8")
        assert "../widgets/chat_transcript.py" in sources
        assert "../widgets/chat_input_box.py" in sources

        content = (_I18N_DIR / "hve_gui_en_US.ts").read_text(encoding="utf-8")
        for name in ("ChatTranscriptView", "ChatInputBox"):
            assert f"<context>\n    <name>{name}</name>" in content, name
            context = content.split(f"<name>{name}</name>", 1)[1].split("</context>", 1)[0]
            assert 'type="unfinished"' not in context, name

        input_context = content.split("<name>ChatInputBox</name>", 1)[1].split("</context>", 1)[0]
        assert "<source>中断して送信</source>" in input_context

    def test_toolsearch_settings_section_is_translated(self) -> None:
        """FR-GUI-07: Tool-Search セクションの文言が翻訳カタログに載っていること。"""
        sources = (_I18N_DIR / "translations.pro").read_text(encoding="utf-8")
        assert "../toolsearch_settings_section.py" in sources

        content = (_I18N_DIR / "hve_gui_en_US.ts").read_text(encoding="utf-8")
        for name in ("ToolSearchSection", "_KeyValueTable"):
            assert f"<context>\n    <name>{name}</name>" in content, name
            context = content.split(f"<name>{name}</name>", 1)[1].split("</context>", 1)[0]
            assert 'type="unfinished"' not in context, name

    def test_toolsearch_policy_hints_are_translated(self) -> None:
        """FR-GUI-07: ポリシー編集項目の説明が英語でも表示できること。"""
        from hve.gui import help_content as hc

        content = (_I18N_DIR / "hve_gui_en_US.ts").read_text(encoding="utf-8")
        context = content.split("<name>help_content</name>", 1)[1].split("</context>", 1)[0]
        for field in hc._TOOLSEARCH_POLICY_HELP:
            source = hc._TOOLSEARCH_POLICY_HELP[field].short
            block = context.split(f"<source>{_escape(source)}</source>", 1)
            assert len(block) == 2, field
            assert 'type="unfinished"' not in block[1].split("</message>", 1)[0], field

    def test_adi_section_is_translated_without_removed_workflow_residue(self) -> None:
        """ADI 統合後の C17 文言が完訳され、廃止workflow文脈を含まないこと。"""
        content = (_I18N_DIR / "hve_gui_en_US.ts").read_text(encoding="utf-8")
        context = content.split("<name>_C17ADI</name>", 1)[1].split("</context>", 1)[0]
        assert "<source>対象設計書フォルダを選択</source>" in context
        assert "<source>分析の深さ</source>" in context
        assert "<source>分析の観点</source>" in context
        assert 'type="unfinished"' not in context
        removed_workflow = "AQ" + "OD"
        assert f"_C12{removed_workflow}" not in content
        assert removed_workflow not in content

    def test_qa_answer_dialog_is_translated(self) -> None:
        """FR-GUI-29: QA 回答ダイアログの文言が翻訳カタログに載っていること。"""
        sources = (_I18N_DIR / "translations.pro").read_text(encoding="utf-8")
        assert "../qa_answer_dialog.py" in sources

        content = (_I18N_DIR / "hve_gui_en_US.ts").read_text(encoding="utf-8")
        assert '<context>\n    <name>QAAnswerDialog</name>' in content
        context = content.split("<name>QAAnswerDialog</name>", 1)[1].split("</context>", 1)[0]
        assert "<source>質問票をコピー</source>" in context
        assert "<source>Work IQ 用プロンプトをコピー</source>" in context
        assert 'type="unfinished"' not in context

    def test_github_comment_and_picker_are_translated(self) -> None:
        """FR-GUI-30 / FR-GUI-32: 新規 GitHub UI の文言が翻訳カタログに載っていること。"""
        sources = (_I18N_DIR / "translations.pro").read_text(encoding="utf-8")
        assert "../github_comment_editor.py" in sources
        assert "../github_picker_dialog.py" in sources

        content = (_I18N_DIR / "hve_gui_en_US.ts").read_text(encoding="utf-8")
        for name in ("GitHubCommentEditor", "GitHubPickerDialog"):
            assert f"<context>\n    <name>{name}</name>" in content, name
            context = content.split(f"<name>{name}</name>", 1)[1].split("</context>", 1)[0]
            assert 'type="unfinished"' not in context, name

        editor = content.split("<name>GitHubCommentEditor</name>", 1)[1].split("</context>", 1)[0]
        for source in ("編集", "プレビュー", "太字", "タスクリスト"):
            assert f"<source>{source}</source>" in editor, source

    def test_github_branch_and_console_actions_are_translated(self) -> None:
        """FR-GUI-33 / FR-GUI-34: PR パネルの新規操作が翻訳済みであること。"""
        content = (_I18N_DIR / "hve_gui_en_US.ts").read_text(encoding="utf-8")
        context = content.split("<name>GitHubPullRequestPanel</name>", 1)[1].split(
            "</context>", 1
        )[0]
        for source in (
            "現在のブランチを push",
            "head ブランチを削除",
            "コンソール出力を投稿",
        ):
            assert f"<source>{source}</source>" in context, source
        assert 'type="unfinished"' not in context

    def test_github_task_and_issue_metadata_are_translated(self) -> None:
        """FR-GUI-40 / 41: Current Task と Issue metadata 文言が翻訳済みであること。"""
        content = (_I18N_DIR / "hve_gui_en_US.ts").read_text(encoding="utf-8")
        issue_context = content.split("<name>GitHubIssuePanel</name>", 1)[1].split(
            "</context>", 1
        )[0]
        for source in (
            "ラベル",
            "担当者",
            "マイルストーン",
            "作成候補を取得",
            "作成後、このタスクに関連付ける",
            "リポジトリが変更されたため、古い作成候補を破棄しました。",
        ):
            assert f"<source>{_escape(source)}</source>" in issue_context, source
        assert (
            "<source>ラベル &apos;{value}&apos; は反映されませんでした。</source>"
            in issue_context
        )
        assert 'type="unfinished"' not in issue_context

        window_context = content.split("<name>GitHubWindow</name>", 1)[1].split(
            "</context>", 1
        )[0]
        for source in ("現在のタスク", "関連付けなし", "Issue の関連付けを解除"):
            assert f"<source>{source}</source>" in window_context, source
        assert 'type="unfinished"' not in window_context

    def test_github_pull_request_creation_is_translated(self) -> None:
        """FR-GUI-42 / 43: PR 作成・後処理の主要文言が翻訳済みであること。"""
        content = (_I18N_DIR / "hve_gui_en_US.ts").read_text(encoding="utf-8")
        context = content.split("<name>GitHubPullRequestPanel</name>", 1)[1].split(
            "</context>", 1
        )[0]
        for source in (
            "Pull Request を作成",
            "作成前チェック",
            "既定テンプレートを読み込む",
            "default branch への merge 時に Issue を閉じる",
            "レビュアー（ユーザー名、カンマ区切り）",
            "レビュアーチーム（slug、カンマ区切り）",
            "metadata を再試行",
            "分類できない後処理エラー（安全のため再試行不可）",
        ):
            assert f"<source>{source}</source>" in context, source
        assert 'type="unfinished"' not in context

    def test_compiled_catalog_is_not_stale(self) -> None:
        """`.ts` だけ更新して `.qm` を再生成し忘れると英語 UI に反映されない。"""
        from PySide6.QtWidgets import QApplication

        from hve.gui import help_content as hc

        qm_path = _I18N_DIR / "hve_gui_en_US.qm"
        if not qm_path.exists():
            pytest.skip(".qm not built; run setup-hve to compile")
        app = QApplication.instance() or QApplication(sys.argv[:1])
        try:
            assert i18n.install_translator(app, "en_US") is True
            assert app.translate("ToolSearchSection", "保存") == "Save"
            assert app.translate("_KeyValueTable", "行を追加") == "Add row"
            assert (
                app.translate("_C17ADI", "対象設計書フォルダを選択")
                == "Select design document folder"
            )
            assert app.translate("_C17ADI", "分析の深さ") == "Analysis depth"
            assert (
                app.translate("QAAnswerDialog", "質問票をコピー") != "質問票をコピー"
            )
            assert (
                app.translate("QAAnswerDialog", "Work IQ 用プロンプトをコピー")
                != "Work IQ 用プロンプトをコピー"
            )
            assert app.translate("GitHubCommentEditor", "プレビュー") == "Preview"
            assert app.translate("GitHubPickerDialog", "Issue を選択") == "Select an issue"
            assert (
                app.translate("GitHubPullRequestPanel", "head ブランチを削除")
                == "Delete head branch"
            )
            assert (
                app.translate("_C5IssuePR", "連携する Pull Request 番号")
                == "Pull request number to link"
            )
            hint = hc._TOOLSEARCH_POLICY_HELP["limit"].short
            assert app.translate("help_content", hint) != hint
        finally:
            i18n.install_translator(app, "ja_JP")


class TestAvailableLanguages:
    def test_includes_auto_ja_en(self) -> None:
        langs = i18n.available_languages()
        codes = [code for code, _ in langs]
        assert "auto" in codes
        assert "ja_JP" in codes
        assert "en_US" in codes
