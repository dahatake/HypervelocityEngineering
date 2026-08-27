"""T-α: 契約 SSOT ドリフト検出テスト。

validator が強制する canonical 定義（registration marker / static-verification.log
の path 形）と、生成側（Prompt / template / Skill）の記述が一致することを固定する。
片方だけが変わる契約ドリフト（memo §17 / §19 / §20）を CI で検出し、Raw-Log-Path や
登録 marker が run ごとに揺れて Step が停止する再発を防ぐ。

方針（plan v2 T-α / Q4=A: ドリフト検出テストのみ）: validator 側の既存定義を SSOT と
し、生成側テキストがそれに追随していることを assert する。新しい共有定数 module は
導入しない（YAGNI）。
"""
from __future__ import annotations

import inspect
from pathlib import Path

from hve import runner as runner_module
from hve.artifact_validation import (
    _ASDW_AUDIT_REGISTRATION_BEGIN,
    _ASDW_AUDIT_REGISTRATION_END,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _read(rel: str) -> str:
    return (_REPO_ROOT / rel).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# registration marker SSOT（validator 定数 ↔ 生成側 Skill contract）
# ---------------------------------------------------------------------------
_VERIFIER_CONTRACT = (
    ".github/skills/azure-skills/azure-cli-deploy-scripts/references/"
    "asdw-data-verifier-contract.md"
)


def test_registration_marker_constants_match_generation_contract() -> None:
    """validator の marker 定数が生成側 Skill contract に verbatim で存在する。"""
    contract = _read(_VERIFIER_CONTRACT)
    assert _ASDW_AUDIT_REGISTRATION_BEGIN in contract
    assert _ASDW_AUDIT_REGISTRATION_END in contract


def test_registration_marker_constants_are_the_documented_tokens() -> None:
    """marker 定数値を pin（変更時は Skill contract の更新も強制する双方向 lock）。"""
    assert _ASDW_AUDIT_REGISTRATION_BEGIN == "# HVE-AUDIT-REGISTRATION-BEGIN"
    assert _ASDW_AUDIT_REGISTRATION_END == "# HVE-AUDIT-REGISTRATION-END"


# ---------------------------------------------------------------------------
# static-verification.log path SSOT（runner gate ↔ 生成側 Prompt/template）
# ---------------------------------------------------------------------------
_LOG_FILENAME = "static-verification.log"
_STEP12_PROMPT = ".github/prompts/Dev-Microservice-Azure-DataTestCoding.prompt.md"
_STEP12_TEMPLATE = ".github/prompts/steps/asdw-web/step-1.2.prompt.md"


def test_static_verification_log_filename_matches_runner_gate() -> None:
    """runner gate が開く log filename と生成側 Prompt/template が一致する。"""
    runner_source = inspect.getsource(
        runner_module.StepRunner._validate_asdw_data_static_verification_log
    )
    assert _LOG_FILENAME in runner_source
    assert _LOG_FILENAME in _read(_STEP12_PROMPT)
    assert _LOG_FILENAME in _read(_STEP12_TEMPLATE)


def test_static_verification_log_canonical_posix_path_in_generation() -> None:
    """生成側は canonical な repository-relative POSIX('/') path を規定する。

    memo §19 の drift（Windows '\\' 区切り・N/A 記録）を防ぐため、'/' 区切りの
    canonical path・Raw-Log-Path 連携・N/A 禁止が生成側に明記されていること。
    """
    posix_fragment = f"step-1-2/<target-app-id>/RED/{_LOG_FILENAME}"
    backslash_fragment = f"step-1-2\\<target-app-id>\\RED\\{_LOG_FILENAME}"
    for rel in (_STEP12_PROMPT, _STEP12_TEMPLATE):
        text = _read(rel)
        # canonical '/' 区切りの path を規定していること
        assert posix_fragment in text, rel
        # memo §19 のセパレータ drift を直接ロック: Windows '\\' 版 path を書かない
        assert backslash_fragment not in text, rel
        # Raw-Log-Path 連携と N/A 記録禁止の規定が存在すること
        assert "Raw-Log-Path" in text, rel
        assert "N/A" in text, rel
