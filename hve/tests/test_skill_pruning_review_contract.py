"""Skill pruning のユーザーレビューで確定した RED 契約。"""

from __future__ import annotations

from pathlib import Path, PurePosixPath

import yaml  # type: ignore

_ROOT = Path(__file__).resolve().parents[2]
_SKILLS = _ROOT / ".github" / "skills"
_EVALS = _SKILLS / "_evals"
_ROUTING = _SKILLS / "_routing" / "README.md"
_DOCS_OUTPUT = _SKILLS.joinpath("docs-output-format", "SKILL.md")
_LARGE_OUTPUT = _SKILLS.joinpath("large-output-chunking", "SKILL.md")
_TDD_REALITY = _SKILLS.joinpath("tdd-red-green-reality", "SKILL.md")
_TDD_POLICY_REF = _SKILLS.joinpath(
    "tdd-red-green-reality", "references", "generated-test-policy.md"
)
_DATAFLOW_STRATEGY = _SKILLS.joinpath(
    "dataflow-design-guide", "references", "dataflow-test-strategy.md"
)
_TEST_STRATEGY = _ROOT / "docs" / "catalog" / "test-strategy.md"
_DATAFLOW_TESTSPEC_PROMPT = _ROOT.joinpath(
    ".github", "prompts", "Arch-Dataflow-TDD-TestSpec.prompt.md"
)
_WORKFLOW_REFERENCE = _ROOT / "users-guide" / "workflow-reference.md"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _frontmatter(path: Path) -> dict[str, object]:
    text = _read(path)
    parts = text.split("---", 2)
    assert len(parts) == 3 and not parts[0].strip(), f"{path} has no frontmatter"
    value = yaml.safe_load(parts[1])
    assert isinstance(value, dict), f"{path} frontmatter must be a mapping"
    return value


def _description(path: Path) -> str:
    frontmatter = _frontmatter(path)
    description = frontmatter.get("description")
    assert isinstance(description, str), f"{path} has no description"
    return description


def _required_bullets(text: str, heading: str) -> list[str]:
    assert heading in text, f"missing heading: {heading}"
    section = text.split(heading, 1)[1].split("\n## ", 1)[0]
    assert "### 必須" in section, f"{heading} has no required block"
    required = section.split("### 必須", 1)[1]
    cutoffs = [
        index
        for marker in ("\n### ", "\n---")
        if (index := required.find(marker)) >= 0
    ]
    if cutoffs:
        required = required[: min(cutoffs)]
    return [line.strip() for line in required.splitlines() if line.startswith("- ")]


def test_eval_skill_paths_resolve_local_skills_or_use_canonical_external_format() -> None:
    eval_files = sorted(_EVALS.glob("*.eval.yaml"))
    assert eval_files, "no skill eval files found"
    errors: list[str] = []

    for eval_file in eval_files:
        evaluation = yaml.safe_load(_read(eval_file))
        assert isinstance(evaluation, dict), f"{eval_file} must be a YAML mapping"
        skill_name = evaluation.get("skill")
        skill_path = evaluation.get("skill_path")
        if not isinstance(skill_name, str) or not isinstance(skill_path, str):
            errors.append(f"{eval_file.name}: skill and skill_path must be strings")
            continue

        path = PurePosixPath(skill_path)
        if skill_path.startswith("~"):
            valid = (
                "\\" not in skill_path
                and len(path.parts) >= 5
                and ".." not in path.parts
                and path.parts[:3] == ("~", ".agents", "skills")
                and path.parts[-2:] == (skill_name, "SKILL.md")
            )
            if not valid:
                errors.append(f"{eval_file.name}: non-canonical external path {skill_path}")
            continue

        candidate = (_ROOT / path).resolve()
        if _ROOT.resolve() not in candidate.parents:
            errors.append(f"{eval_file.name}: path escapes repository: {skill_path}")
            continue
        if not candidate.is_file():
            errors.append(f"{eval_file.name}: missing local Skill {skill_path}")
            continue
        frontmatter = _frontmatter(candidate)
        if frontmatter.get("name") != skill_name:
            errors.append(
                f"{eval_file.name}: eval name {skill_name!r} != "
                f"frontmatter name {frontmatter.get('name')!r}"
            )

    assert not errors, "\n".join(errors)


def test_application_requirement_traceability_is_active_in_routing() -> None:
    relative = ".github/skills/application-requirement-traceability/SKILL.md"
    assert (_ROOT / relative).is_file()
    rows = [
        line
        for line in _read(_ROUTING).split("## Skill Deprecation", 1)[0].splitlines()
        if "`application-requirement-traceability`" in line
    ]
    assert rows, "application-requirement-traceability is not actively routed"
    assert any(f"`{relative}`" in row for row in rows)


def test_docs_output_format_description_excludes_test_specs_and_work_artifacts() -> None:
    description = _description(_DOCS_OUTPUT)
    excluded = description.split("DO NOT USE FOR:", 1)[1].split("WHEN:", 1)[0]
    assert "work/" in excluded
    assert "test spec format" in excluded or "テスト仕様書のフォーマット" in excluded


def test_large_output_chunking_description_exposes_write_safety_triggers() -> None:
    description = _description(_LARGE_OUTPUT)
    use_for = description.split("USE FOR:", 1)[1].split("DO NOT USE FOR:", 1)[0]
    for phrase in (
        "write safety",
        "staged writing",
        "read verification",
        "retry on write failure",
    ):
        assert phrase in use_for
    when = description.split("WHEN:", 1)[1]
    assert "terminal output" in when
    assert "50,000" not in description


def test_large_output_chunking_points_to_runtime_write_size_canonical_rule() -> None:
    text = _read(_LARGE_OUTPUT)
    assert "1 回の書込みは 300 行以内" in text
    assert ".github/prompts/runtime/runner/runtime-guidance-suffix.prompt.md" in text
    assert "最大 3 回" in text
    assert "50,000" not in text


def test_tdd_reality_uses_active_policy_and_current_cli_mcp_registration() -> None:
    active = _read(_ROUTING).split("## Skill Deprecation", 1)[0]
    assert ".github/skills/tdd-red-green-reality/SKILL.md" in active
    text = _read(_TDD_REALITY)
    assert ".github/.mcp.json" not in text
    for phrase in ("agent-common-preamble", "Copilot CLI", "`/mcp`"):
        assert phrase in text


def test_dataflow_test_strategy_preserves_approved_required_items_only() -> None:
    text = _read(_DATAFLOW_STRATEGY)
    expected = {
        "## 1. テストピラミッド": [
            "- データフロー処理におけるテストレイヤーの配分方針",
        ],
        "## 2. テストデータ生成戦略": [
            "- テストデータの生成方法（ファクトリ/フィクスチャ/本番データのサニタイズ）",
            "- テストデータのボリューム方針（ユニット: 少量、E2E: 本番相当）",
            "- エッジケースデータの定義方針",
        ],
        "## 4. データ品質テスト": [
            "- 入力データ品質チェック（NULL率・型チェック・範囲チェック）",
            "- 出力データ品質チェック（行数整合・集計値検証）",
            "- データ品質メトリクスの定義",
        ],
        "## 5. E2E テスト方針": [
            "- E2E テストの実行環境（ステージング/専用環境）",
            "- テストシナリオの定義方針（正常系/異常系/リカバリ）",
            "- テストデータのセットアップ・クリーンアップ方針",
        ],
        "## 6. CI/CD パイプラインとの統合": [
            "- 各テストレイヤーの実行タイミング（PR時/マージ時/定期実行）",
            "- テスト失敗時のゲート方針（ブロック/警告）",
        ],
        "## 7. カバレッジ方針": [
            "- コードカバレッジの目標値（ライン/ブランチ）",
            "- カバレッジ除外対象の方針",
        ],
    }
    problems = [
        f"{heading}: missing approved item: {bullet}"
        for heading, bullets in expected.items()
        for bullet in bullets
        if bullet not in _required_bullets(text, heading)
    ]
    forbidden = (
        "各表の列は出力スキーマとして扱い、削除・名称変更しない",
        "HVE バッチ固有の入力ファイル、抽出元、ロード先、再実行時データを区別する方針",
        "バッチ実行単位での検知タイミング、失敗時アクション、証跡の保存先",
        "入力配置から出力検証までのバッチ固有クリティカルパス",
    )
    problems.extend(f"unapproved clause: {phrase}" for phrase in forbidden if phrase in text)
    assert not problems, "\n".join(problems)


def test_arch_dataflow_tdd_testspec_cites_reachable_strategy_sections() -> None:
    prompt = _read(_DATAFLOW_TESTSPEC_PROMPT)
    extraction = prompt.split("### 5.2 抽出（推測しない）", 1)[1].split(
        "### 5.3 計画・分割", 1
    )[0]
    strategy = _read(_TEST_STRATEGY)
    assert "## 2. テスト分類定義" in strategy
    assert "### 5.1 バッチ／データフロー処理テスト方針（該当 SVC のみ）" in strategy
    assert "2. テスト分類定義" in extraction
    assert "5.1 バッチ／データフロー処理テスト方針（該当 SVC のみ）" in extraction
    assert "2. バッチ固有テスト種別" not in extraction
    assert "3. テストデータ戦略" not in extraction
    assert "### テストデータ戦略" in _read(_TDD_POLICY_REF)
    assert "tdd-red-green-reality" in extraction and "テストデータ戦略" in extraction
    producer = _read(_ROOT / ".github/prompts/Arch-TDD-TestStrategy.prompt.md")
    assert "## 2. テスト分類定義" in producer
    assert "## 5.1 バッチ／データフロー処理テスト方針" in producer
    assert "§1 のテストピラミッド" not in prompt
    assert "§2 のテスト分類定義" in prompt
    assert "未定義の種別" in extraction and "TBD" in extraction
    assert "§8 `### 3.1`〜`### 3.6` の6テスト種別" in prompt


def test_workflow_reference_describes_major_skills_and_links_routing() -> None:
    text = _read(_WORKFLOW_REFERENCE)
    before_app_id = text.split("\n## APP-ID 指定方法", 1)[0]
    section = before_app_id[before_app_id.rfind("\n## ") :]
    assert "主要 Skill" in section
    assert "全 Skills" not in section
    routing_link = "../.github/skills/_routing/README.md"
    assert routing_link in section
    assert (_WORKFLOW_REFERENCE.parent / routing_link).resolve().is_file()


class TestAstraT01SkillPruningReviewContract:
    def test_astra_s01_contributing_treats_1024_as_known_copilot_guidance(self) -> None:
        text = _read(_SKILLS / "CONTRIBUTING.md")
        heading = "## 3. description 文字数の推奨"
        assert heading in text
        section = text.split(heading, 1)[1].split("\n---", 1)[0]

        assert "GitHub Copilot" in section
        assert "1024" in section
        assert "description" in section and "全体" in section
        assert "未確定" not in section

    def test_astra_s07_knowledge_lookup_root_uses_real_guide_conditionally(self) -> None:
        path = _SKILLS / "knowledge-lookup" / "SKILL.md"
        detail_path = _SKILLS / "knowledge-lookup" / "references" / "detail.md"
        root = _read(path)
        detail = _read(detail_path)

        assert detail_path.is_file()
        assert "既存の直接参照を優先する" in detail
        assert "以下の場合は「不明瞭」に該当 **しない**" in detail
        assert "### Step 5: 情報が見つからなかった場合の振る舞い（段階的ルール）" in detail
        assert "knowledge/ は読み取り専用" in detail

        assert "references/detail.md" in root
        assert "十分" in root and any(
            phrase in root for phrase in ("不要", "使わない", "参照しない")
        )
        assert "直接参照" in root and "優先" in root
        assert "読み取り専用" in root
        assert "未確定" in root or "根拠不足" in root or "該当情報なし" in root

    def test_astra_s08_knowledge_management_root_links_real_synthesis_guide(self) -> None:
        path = _SKILLS / "knowledge-management" / "SKILL.md"
        guide_path = (
            _SKILLS
            / "knowledge-management"
            / "references"
            / "knowledge-management-guide.md"
        )
        root = _read(path)
        guide = _read(guide_path)

        assert guide_path.is_file()
        for source_anchor in (
            "## §2 D01〜D21 分類マッピングルール",
            "## §11 内容合成プロセス（Content Synthesis）",
            "## §12 差分マージ戦略（Incremental Merge）",
        ):
            assert source_anchor in guide

        assert "references/knowledge-management-guide.md" in root
        assert "D01〜D21" in root
        assert "内容合成" in root
        assert "マージ" in root
        assert "整合性" in root or "確認" in root

    def test_astra_s09_input_description_prioritizes_agent_override(self) -> None:
        path = _SKILLS / "input-file-validation" / "SKILL.md"
        reference_path = path.parent / "references" / "missing-file-handling.md"
        description = _description(path)
        reference = _read(reference_path)

        assert reference_path.is_file()
        assert "Agent 固有オーバーライドがある？" in reference
        assert "停止設定" in reference
        assert "質問設定" in reference
        assert "TBD記載で続行" in reference

        assert "Agent 固有" in description or "オーバーライド" in description
        assert "停止" in description
        assert "質問" in description
        assert "TBD" in description
        assert "欠損ファイルに対して TBD 記載で続行する" not in description

    def test_astra_s10_questionnaire_description_keeps_control_markers(self) -> None:
        path = _SKILLS / "task-questionnaire" / "SKILL.md"
        description = _description(path)
        body = _read(path)

        assert "<!-- auto-context-review: true -->" in body
        assert "Prompt Edition request preflight" in body

        assert "auto-context-review" in description
        assert "Prompt Edition request preflight" in description
        assert "回答待ち" in body or "作業を進めない" in body