# ADR-0003: ARD ワークフロー Fan-out 再設計（ADR-0002 O-1 再評価）

<!-- task_scope=multi context_size=large phase=0 priority=high date=2026-05-12 -->

| 項目 | 内容 |
|---|---|
| **ステータス** | Proposed |
| **日付** | 2026-05-12 |
| **対象** | `hve/` の `ARD` ワークフロー（事業分析 → ユースケースカタログ） |
| **関連** | [ADR-0002](ADR-0002-hve-fanout-architecture.md), [hve/workflow_registry.py](../../hve/workflow_registry.py), [hve/catalog_parsers.py](../../hve/catalog_parsers.py) |

---

## 1. 背景と課題

[ADR-0002](ADR-0002-hve-fanout-architecture.md) §2 で「O-1: ARD は fan-out 対象外」と決定したが、本リポジトリのサブタスク再設計（チャット起点・2026-05-12）で **ユーザーから明示的に再評価指示**を受領した。本 ADR で ARD への fan-out 適用を提案する。

### 既存 ARD の制約（事実ベース）

- 現状の ARD は 3 step（1: 事業分析（対象未定）、2: 事業分析（対象指定済）、3: ユースケース作成）の単線 DAG ([hve/workflow_registry.py](../../hve/workflow_registry.py))。
- 各 step は単一 `CopilotClient` セッションで 1 Markdown を一括生成する。
  - `docs/company-business-requirement.md`（Step 1, 対象未定時）
  - `docs/business-requirement.md`（Step 2, 対象指定時）
  - `docs/catalog/use-case-catalog.md`（Step 3）
- `max_parallel` は workflow 単位で未指定（DAGExecutor 既定 15 にフォールバック）。

### 解決したい要件

1. **Context Window の最小化**: 事業候補・ユースケース 1 件 = 1 サブタスクに分割し、単一セッションでの長文生成を避ける。
2. **並列度の最大化**: 業務候補列挙後の per-business 分析、ユースケース骨格抽出後の per-UC 詳細生成。
3. **対象未定 / 指定済 の両モード対応**: 既存の `skip_fallback_deps` セマンティクスを継承。
4. **既存実行履歴との互換性**: 旧 `RunState` (step_id="1","2","3") から再開するシナリオで致命的エラーを発生させない（warning のみ）。

---

## 2. 決定サマリ表（不明点と採用案）

| 不明点 | 採用 | 概要 |
|---|---|---|
| O-1 再評価 | O-1' | ADR-0002 の「ARD 対象外」を**撤回**し、ARD に fan-out を適用する |
| 業務候補 ID 体系 | BIZ-NN | 2 桁ゼロパディング（`BIZ-01`, `BIZ-02`, ...）。`APP-NN` 形式に倣う |
| 業務候補上限 | 10 件 | 業務候補は通常 5〜10 件。過剰並列防止のためデフォルト上限 |
| UC 骨格 ID 体系 | UC-* | 既存 ユースケースカタログの UC- プレフィックス継承 |
| UC 詳細上限 | 50 件 | 大規模事業でも上限。max_fanout_keys で制御 |
| 動的パーサ | F-2 拡張 | `business_candidate` / `use_case_skeleton` を `catalog_parsers.py` に追加 |
| 既存履歴互換 | warning + 新規実行 | 旧 step_id を持つ resume_state は warning ログ後に新規実行扱い |

「**この回答は Copilot 推論をしたものです。**」

---

## 3. 設計の核

### 3.1 新 7 step 構成

```
[Step 1] 事業分野候補列挙（対象未定時のみ、target_business 指定時はスキップ）
   ↓ docs/company-business-recommendation.md（BIZ-NN リスト）
[Step 1.1] 事業分野別深掘り分析（fan-out: business_candidate / N 並列）
   ↓ docs/business/{BIZ-NN}-analysis.md（N 件）
[Step 1.2] 事業分析統合（join）
   ↓ docs/company-business-requirement.md
[Step 2] 対象業務深掘り分析（target_business 指定時のみ、skip_fallback_deps=[1.2]）
   ↓ docs/business-requirement.md
[Step 3.1] ユースケース骨格抽出（depends_on=[2] / skip_fallback_deps=[1.2]）
   ↓ docs/catalog/use-case-skeleton.md（UC-* リスト）
[Step 3.2] ユースケース詳細生成（fan-out: use_case_skeleton / N 並列）
   ↓ docs/use-cases/{UC-*}-detail.md（N 件）
[Step 3.3] ユースケースカタログ統合（join）
   ↓ docs/catalog/use-case-catalog.md
```

### 3.2 StepDef 定義（実装目安）

```python
ARD = WorkflowDef(
    id="ard",
    name="Auto Requirement Definition",
    label_prefix="ard",
    state_labels=_make_state_labels("ard"),
    params=["company_name", "target_business", ...],
    max_parallel=15,
    steps=[
        StepDef(id="1", title="事業分野候補列挙",
                custom_agent="Arch-ARD-BusinessAnalysis-Untargeted",
                consumed_artifacts=[],
                output_paths=["docs/company-business-recommendation.md"],
                body_template_path="templates/ard/step-1.md"),
        StepDef(id="1.1", title="事業分野別深掘り分析",
                custom_agent="Arch-ARD-BusinessAnalysis-Untargeted",
                depends_on=["1"],
                consumed_artifacts=[],
                fanout_parser="business_candidate",
                output_paths_template=["docs/business/{key}-analysis.md"],
                body_template_path="templates/ard/step-1.1.md",
                additional_prompt_template_path="hve/prompt/fanout/ard/_common.md"),
        StepDef(id="1.2", title="事業分析統合",
                custom_agent="Arch-ARD-BusinessAnalysis-Untargeted",
                depends_on=["1.1"],
                consumed_artifacts=[],
                output_paths=["docs/company-business-requirement.md"],
                body_template_path="templates/ard/step-1.2.md"),
        StepDef(id="2", title="対象業務深掘り分析",
                custom_agent="Arch-ARD-BusinessAnalysis-Targeted",
                skip_fallback_deps=["1.2"],
                consumed_artifacts=[],
                output_paths=["docs/business-requirement.md"],
                body_template_path="templates/ard/step-2.md"),
        StepDef(id="3.1", title="ユースケース骨格抽出",
                custom_agent="Arch-ARD-UseCaseCatalog",
                depends_on=["2"],
                skip_fallback_deps=["1.2"],
                consumed_artifacts=[],
                output_paths=["docs/catalog/use-case-skeleton.md"],
                body_template_path="templates/ard/step-3.1.md"),
        StepDef(id="3.2", title="ユースケース詳細生成",
                custom_agent="Arch-ARD-UseCaseCatalog",
                depends_on=["3.1"],
                consumed_artifacts=[],
                fanout_parser="use_case_skeleton",
                output_paths_template=["docs/use-cases/{key}-detail.md"],
                body_template_path="templates/ard/step-3.2.md",
                additional_prompt_template_path="hve/prompt/fanout/ard/_common.md"),
        StepDef(id="3.3", title="ユースケースカタログ統合",
                custom_agent="Arch-ARD-UseCaseCatalog",
                depends_on=["3.2"],
                consumed_artifacts=[],
                output_paths=["docs/catalog/use-case-catalog.md"],
                body_template_path="templates/ard/step-3.3.md"),
    ],
)
```

### 3.3 動的パーサ（[hve/catalog_parsers.py](../../hve/catalog_parsers.py) 追加）

- `parse_business_candidate(repo_root)` → `BIZ-NN` ID 抽出（`docs/company-business-recommendation.md`、表 または `## BIZ-NN` 見出し）
- `parse_use_case_skeleton(repo_root)` → `UC-*` ID 抽出（`docs/catalog/use-case-skeleton.md`）

ID パターン（推論）:
- `_BIZ_ID_PATTERN = r"BIZ-\d{2,3}"`
- `_UC_ID_PATTERN = r"UC-[A-Za-z0-9_\-]+"`

「**この回答は Copilot 推論をしたものです。**」

### 3.4 既存実行履歴との互換性

旧 RunState (step_id ∈ {"1","2","3"}) からの resume:
- `resume_state.selected_step_ids` に旧 ID が含まれる場合、Sub-10 実装時に以下のいずれか:
  - (a) 新 step_id "1" は旧 step_id "1" と意味が変わる（旧: 全文生成、新: 候補列挙のみ）→ warning + 再実行
  - (b) 旧 ID "2", "3" → 新の "2", "3.1"+"3.2"+"3.3" にマップ不能 → warning + 新規実行扱い
- 上記は `orchestrator.py` の resume 処理に `_ard_legacy_state_warning` を追加して可観測化する。

---

## 4. 非対象 (Non-goals)

- 既存 ARD `templates/ard/step-1.md`、`step-2.md`、`step-3.md` の内容更新は Sub-10 で実施。
- 業務候補抽出の AI ロジック自体（LLM 出力品質）は本 ADR の対象外。
- 旧 step_id を持つ古い resume_state からの自動マイグレーションは対象外（warning + 新規実行のみ）。

---

## 5. 影響範囲

- [hve/workflow_registry.py](../../hve/workflow_registry.py) ARD 定義
- [hve/catalog_parsers.py](../../hve/catalog_parsers.py) 新規パーサ 2 種
- `.github/scripts/templates/ard/` 新規テンプレート 5 件（step-1.md は更新）
- `hve/prompt/fanout/ard/_common.md` 新規
- `hve/tests/test_workflow_registry_ard.py`、`test_orchestrator_ard.py` 更新

---

## 6. 検証

- DAG 形状テスト: 7 step 構成、fan-out 子展開、`skip_fallback_deps` セマンティクス
- e2e dry-run: `python -m hve orchestrate --workflow ard --dry-run`
- 旧 resume_state を読み込んでも例外を投げないこと（warning のみ）

---

## 7. 関連 ADR

- [ADR-0002: hve サブタスク Fan-out アーキテクチャ](ADR-0002-hve-fanout-architecture.md) — ARD を「O-1: 対象外」と決定。本 ADR で**撤回**。
