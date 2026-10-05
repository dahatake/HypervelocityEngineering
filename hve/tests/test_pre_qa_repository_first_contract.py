"""FR-QA-09: 事前 QA の Prompt が質問の生成より前に L1（リポジトリ内の検索）を指示する契約。"""

from hve.prompts import PRE_EXECUTION_QA_PROMPT_V2


def test_pre_execution_qa_prompt_requires_repository_first_l1_search() -> None:
    prompt = PRE_EXECUTION_QA_PROMPT_V2

    assert "質問を生成する前" in prompt
    assert "knowledge/" in prompt
    assert "docs/" in prompt
    assert "qa/" in prompt
    assert "候補が 1 つ" in prompt
    assert "出典パス" in prompt
    assert "質問票に載せない" in prompt
