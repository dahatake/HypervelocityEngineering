"""hve.gui.br_generator — `docs/business-requirement.md` の章単位 fan-out 生成。

7 章（H2 単位）を asyncio.gather で並列に LLM 呼び出しし、章ごとに
マージプロンプトで生成 → 全章結合して `docs/business-requirement.md` に書き出す。

設計判断:
- Copilot SDK の CopilotClient セッションを章ごとに 1 本張る（合計 7 本）。
  orchestrator.py `_run_akm_workiq_ingestion` と同じパターン。
- いずれかの章が失敗した場合、既存章本文があればそれを保持、無ければ
  `## {見出し}\n\n[要追加確認] 生成失敗\n` を入れる（捏造禁止のため空欄補完しない）。
- 並列度 7 は AKM の D01〜D21 (21 並列) と比べて低く、レート制限・タイムアウトの
  リスクを抑制。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable, List, Optional

from .br_parser import find_section_text, read_existing_br, read_preamble
from .br_prompt_builder import SourceDoc, build_merge_prompt, read_source_docs
from .business_requirement_template import BR_SECTIONS, BRSection


OUTPUT_REL_PATH = "docs/business-requirement.md"
DEFAULT_TIMEOUT_SECONDS = 600


@dataclass
class BRGenerationConfig:
    """生成処理の設定。"""

    repo_root: Path
    source_paths: List[Path]
    company_name: Optional[str] = None
    target_business: Optional[str] = None
    model: Optional[str] = None  # None の場合は SDK デフォルトを利用
    cli_path: Optional[str] = None  # Copilot CLI のパス（None で auto-detect）
    github_token: Optional[str] = None
    cli_url: Optional[str] = None  # External server を使う場合
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS


@dataclass
class SectionResult:
    """章 1 件分の生成結果。"""

    section: BRSection
    ok: bool
    text: str  # 成功時は LLM 出力、失敗時は既存章本文 or プレースホルダ
    error: Optional[str] = None


@dataclass
class BRGenerationResult:
    """生成処理全体の結果。"""

    ok: bool
    output_path: Optional[Path]
    sections: List[SectionResult] = field(default_factory=list)
    error: Optional[str] = None  # 全体失敗時のメッセージ

    @property
    def succeeded_count(self) -> int:
        return sum(1 for s in self.sections if s.ok)

    @property
    def failed_count(self) -> int:
        return sum(1 for s in self.sections if not s.ok)


ProgressCallback = Callable[[int, int, str], None]
"""(完了章数, 全章数, 直近完了章の見出し) を受け取るコールバック。"""


def _placeholder_section(section: BRSection, reason: str) -> str:
    """生成失敗時のプレースホルダ章本文（捏造禁止のため空欄を埋めない）。"""
    return (
        f"## {section.heading}\n\n"
        f"[要追加確認] 本章は自動生成に失敗しました（理由: {reason}）。"
        f"添付資料・既存資料を参照のうえ手動で記述してください。\n"
    )


async def _generate_one_section(
    client: Any,
    section: BRSection,
    sources: List[SourceDoc],
    existing_section_text: Optional[str],
    config: BRGenerationConfig,
    progress_callback: Optional[ProgressCallback],
    completed_counter: List[int],
    total: int,
) -> SectionResult:
    """1 章分を生成する（章ごとに独立したセッションを張る）。"""
    from copilot.session import PermissionHandler  # type: ignore

    # Late import to avoid hard dep at module import time
    from ..config import DEFAULT_MODEL, MODEL_AUTO_REASONING_EFFORT, MODEL_AUTO_VALUE
    from ..orchestrator import _create_session_with_auto_reasoning_fallback  # type: ignore
    from ..runner import _extract_text  # type: ignore

    prompt = build_merge_prompt(
        section=section,
        sources=sources,
        existing_section_text=existing_section_text,
        target_business=config.target_business,
        company_name=config.company_name,
    )

    session_opts: dict = {
        "on_permission_request": PermissionHandler.approve_all,
        "streaming": True,
        "session_id": f"br-gen-{section.section_id.lower()}",
    }
    model = config.model
    if model and model != MODEL_AUTO_VALUE:
        session_opts["model"] = model
    else:
        session_opts["model"] = DEFAULT_MODEL
        session_opts["reasoning_effort"] = MODEL_AUTO_REASONING_EFFORT

    try:
        session = await _create_session_with_auto_reasoning_fallback(client, session_opts)
    except Exception as exc:  # セッション作成失敗
        text = existing_section_text or _placeholder_section(section, f"session 作成失敗: {exc}")
        result = SectionResult(section=section, ok=False, text=text, error=str(exc))
        completed_counter[0] += 1
        if progress_callback:
            progress_callback(completed_counter[0], total, section.heading)
        return result

    try:
        response = await session.send_and_wait(prompt, timeout=config.timeout_seconds)
        generated = (_extract_text(response) or "").strip()
        if not generated:
            text = existing_section_text or _placeholder_section(section, "LLM 応答が空")
            result = SectionResult(section=section, ok=False, text=text, error="empty response")
        elif not generated.lstrip().startswith("## "):
            # 見出しが先頭に無い → 章境界が壊れるので先頭に付与する
            generated = f"## {section.heading}\n\n{generated}"
            result = SectionResult(section=section, ok=True, text=generated.rstrip() + "\n")
        else:
            result = SectionResult(section=section, ok=True, text=generated.rstrip() + "\n")
    except Exception as exc:
        text = existing_section_text or _placeholder_section(section, f"LLM 呼び出し失敗: {exc}")
        result = SectionResult(section=section, ok=False, text=text, error=str(exc))
    finally:
        try:
            await session.disconnect()
        except Exception:
            pass

    completed_counter[0] += 1
    if progress_callback:
        progress_callback(completed_counter[0], total, section.heading)
    return result


def _assemble_output(
    sections_results: List[SectionResult],
    existing_preamble: str = "",
) -> str:
    """章別結果を結合して BR Markdown 全体を組み立てる。

    既存ファイルの H1 タイトル + 導入文（プリアンブル）があれば保持する。
    無ければ汎用 H1 を生成する（捏造防止のため、企業名等は埋め込まない）。
    """
    blocks: List[str] = []
    preamble = existing_preamble.strip()
    if preamble:
        blocks.append(preamble)
    else:
        blocks.append("# Business Requirement Document")
    for r in sections_results:
        body = r.text.strip()
        if body:
            blocks.append(body)
    # 各ブロック間に空行 1 行を入れて結合
    return "\n\n".join(blocks) + "\n"


async def generate_business_requirement(
    config: BRGenerationConfig,
    progress_callback: Optional[ProgressCallback] = None,
) -> BRGenerationResult:
    """`docs/business-requirement.md` を章単位 fan-out で生成・更新する。

    既存ファイルがある場合は章別に分解してマージ対象とする。
    成功した章は LLM 出力、失敗した章は既存内容を保持（無ければプレースホルダ）。
    """
    # SDK 利用可否チェック（捏造防止: SDK 不在なら空ファイルを書かない）
    try:
        from copilot import CopilotClient, SubprocessConfig, ExternalServerConfig  # type: ignore
    except ImportError as exc:
        return BRGenerationResult(
            ok=False,
            output_path=None,
            error=f"Copilot SDK が利用できません: {exc}",
        )

    output_path = config.repo_root / OUTPUT_REL_PATH

    # 既存 BR の読み込み（プリアンブルは保持して再書き出し時に先頭へ戻す）
    existing_sections = read_existing_br(output_path)
    existing_preamble = read_preamble(output_path)

    # 添付資料を読み込む
    sources = read_source_docs(config.source_paths)
    if not sources:
        return BRGenerationResult(
            ok=False,
            output_path=None,
            error="読み取り可能な添付資料がありません。",
        )

    # SDK config 構築
    if config.cli_url:
        sdk_cfg = ExternalServerConfig(url=config.cli_url)
    else:
        sdk_cfg = SubprocessConfig(
            cli_path=config.cli_path,
            github_token=config.github_token,
            log_level="error",
        )

    client = CopilotClient(config=sdk_cfg)
    try:
        await client.start()
    except Exception as exc:
        return BRGenerationResult(
            ok=False,
            output_path=None,
            error=f"Copilot CLI の起動に失敗: {exc}",
        )

    completed_counter = [0]
    total = len(BR_SECTIONS)

    try:
        tasks = [
            _generate_one_section(
                client=client,
                section=section,
                sources=sources,
                existing_section_text=find_section_text(existing_sections, section.heading),
                config=config,
                progress_callback=progress_callback,
                completed_counter=completed_counter,
                total=total,
            )
            for section in BR_SECTIONS
        ]
        section_results: List[SectionResult] = await asyncio.gather(*tasks)
    finally:
        try:
            await client.stop()
        except Exception:
            pass

    # 出力組み立て・書き出し（既存プリアンブルを保持）
    output_text = _assemble_output(section_results, existing_preamble=existing_preamble)
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(output_text, encoding="utf-8", newline="\n")
    except OSError as exc:
        return BRGenerationResult(
            ok=False,
            output_path=None,
            sections=section_results,
            error=f"ファイル書き出しに失敗: {exc}",
        )

    overall_ok = all(r.ok for r in section_results)
    return BRGenerationResult(
        ok=overall_ok,
        output_path=output_path,
        sections=section_results,
    )
