"""Pre-QA が長い成果物サマリーから質問票を回収する回帰テスト。"""

from __future__ import annotations

import asyncio
import os
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

from hve import runner as runner_module
from hve.config import SDKConfig
from hve.console import Console
from hve.runner import StepRunner


_ARTIFACT_QUESTIONNAIRE = """\
[Q01]
- 分類項目: 実行範囲
- 重要度: 高
- 質問文: 既定値で処理を継続しますか。
- 選択肢:
  A. 継続する
  B. 停止する
- 未回答時の既定値候補: A. 継続する
- 既定値候補の理由: 実行プロンプトに反する指定がないため
- 未回答のまま進めた場合の影響: 処理方針が既定値に固定される

[Q02]
- 分類項目: 入力
- 重要度: 中
- 質問文: 追加の入力資料はありますか。
- 選択肢:
  A. ない
  B. ある
- 未回答時の既定値候補: A. ない
- 既定値候補の理由: タスクプロンプトに追加資料が指定されていないため
- 未回答のまま進めた場合の影響: 未提示資料は今回の判断に反映されない
"""


class _SummaryOnlySession:
    """質問票本文ではなく成果物サマリーだけを返す最小セッション。"""

    def __init__(self, response: str) -> None:
        self.response = response

    async def send_and_wait(self, _prompt: str, *, timeout: float) -> str:
        del timeout
        return self.response


class TestPreQaArtifactFallback(unittest.TestCase):
    """長いサマリーでも明示された qa artifact を再解析することを検証する。"""

    def test_long_summary_with_qa_artifact_reaches_answer_collection(self) -> None:
        summary = (
            "質問票を `qa/pre-qa-questionnaire.md` に作成しました。"
            "質問票には実行範囲と入力資料に関する確認事項を収録しています。"
            "回答時には保存済みの質問票を参照してください。"
        )
        self.assertGreater(len(summary), 50)
        self.assertNotIn("[Q", summary)
        captured_questions: list[Any] = []

        async def fake_collect_answers(
            _console: Console,
            doc: Any,
            _step_id: str,
            _config: SDKConfig,
        ) -> tuple[str, bool]:
            captured_questions.extend(doc.questions)
            return "", True

        with tempfile.TemporaryDirectory() as temporary_directory:
            repo_root = Path(temporary_directory)
            qa_path = repo_root / "qa" / "pre-qa-questionnaire.md"
            qa_path.parent.mkdir(parents=True)
            qa_path.write_text(_ARTIFACT_QUESTIONNAIRE, encoding="utf-8")

            runner = StepRunner(
                config=SDKConfig(
                    model="gpt-5.5",
                    run_id="pre-qa-artifact-fallback",
                    unattended=True,
                ),
                console=Console(verbose=False, quiet=True),
            )
            session = _SummaryOnlySession(summary)
            original_cwd = Path.cwd()
            try:
                os.chdir(repo_root)
                with mock.patch.object(
                    runner_module,
                    "_collect_qa_answers",
                    new=fake_collect_answers,
                ):
                    pre_qa_context = asyncio.run(
                        runner._run_pre_execution_qa(
                            session=session,
                            client=object(),
                            step_id="3.1",
                            original_prompt="テスト用のタスクプロンプト",
                            custom_agent=None,
                            workflow_id="aas",
                            current_phase=1,
                            total_phases=2,
                        )
                    )
            finally:
                os.chdir(original_cwd)

        self.assertEqual(len(captured_questions), 2)
        self.assertIn("既定値で処理を継続", captured_questions[0].question)
        self.assertIn("追加の入力資料", captured_questions[1].question)
        self.assertIn("## 事前 QA 確認済み情報", pre_qa_context)
        self.assertIn("既定値で処理を継続", pre_qa_context)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
