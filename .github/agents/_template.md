---
name: Agent-Template-PLACEHOLDER
description: <この Agent の責務を 40〜1024 文字で記述。「when/use this/trigger/の場合/のとき/に使用/を使う」のいずれかを必ず含めて起動条件を明示する>
tools: ['read', 'edit', 'search']
metadata:
  version: "0.1.0"
---

<!--
  これは `.github/agents/*.agent.md` 新規作成用のテンプレートです。
  ファイル名先頭の `_` により `validate-agents.py` の検査対象から除外されます
  (AGENT_FILE_SKIP_PREFIXES = ("_",))。

  使い方:
    1. 本ファイルを `.github/agents/<新Agent名>.agent.md` としてコピー
    2. frontmatter の placeholder を全て埋める（必須: name, description, metadata.version）
    3. 本文の各 H2 セクションを埋める（標準見出し順は validate-agents.py STANDARD_HEADING_ORDER 参照）
    4. `## Agent 固有の Skills 依存` セクションは **必ず 1 件以上の Skills を列挙** すること
       （空のまま push すると validate-agents.yml CI が warning を出力する。
        `--strict` モードでは error となる）
    5. レビュー指摘の証跡は `hve/prompts.py` REVIEW_PROMPT の「主タスク成果物への
       反映証跡」表形式に従って完了報告（PR body / completion-report.md）へ記載する
-->

## 共通ルール
> 共通行動規約は `.github/copilot-instructions.md` および Skill `agent-common-preamble` (`.github/skills/agent-common-preamble/SKILL.md`) を継承する。

## 禁止事項

> 共通行動規約 (`.github/copilot-instructions.md` §0 / Skill `agent-common-preamble`) の禁止事項を本 Agent でも明示する。詳細は継承元を参照。

- **捏造禁止**: ID / URL / 数値 / 固有名を根拠なく生成しない。不明は `TBD` または `不明（要確認）` と明記する。
- **無関係変更禁止**: スコープ外のファイル整形・一括リファクタ・不要依存追加を行わない（最小差分）。
- **検証マーカー欠落禁止**: 完了報告に `<!-- validation-confirmed -->` または `## 検証` / `## 検証結果` / `## Validation` を必ず含める。
- **work/ 直接編集禁止**: 既存 `work/` ファイルは「削除 → 新規作成」（Skill `work-artifacts-layout` §4.1）。
- **`original-docs/` 書き込み禁止**: 読み取り専用（追記・削除・変更不可）。
- **ルート `README.md` 変更禁止**: `/README.md` の作成・変更を行わない。
- **秘密情報禁止**: 鍵 / トークン / 個人情報 / 内部 URL 等を成果物に含めない。

## Agent 固有の Skills 依存

<!--
  必須セクション（空にしないこと）。
  本 Agent が依存する Skill (.github/skills/<skill-name>/SKILL.md) を列挙する。
  空のままだと validate-agents.py が warning を出力する（QA 可視化）:
    "Section '## Agent 固有の Skills 依存' exists but is empty"
  最低 1 件を必ず記載する。継承のみで十分な場合も `agent-common-preamble` を明記する。
-->

- `agent-common-preamble` — Agent 共通行動規約・禁止事項の継承
- `input-file-validation` — 必読入力ファイルの存在確認と欠損時のデフォルト処理
- `work-artifacts-layout` — `work/<Agent名>/Issue-<識別子>/` 配下の成果物構造
- `<add-more-skills-here>` — <依存理由を 1 行で>

## 1) 目的と非目的

- **目的**: <この Agent が達成するゴールを 1〜3 行で>
- **非目的**: <スコープ外を明示。混入しやすい論点を優先>

## 2) 入力（必ず参照）

- `<path/to/required-input.md>` — <参照理由>
- 入力欠損時は Skill `input-file-validation` の規約に従い、TBD で続行するか中断するかを判断する

## 3) 出力フォーマット（Markdown固定スキーマ）

- 出力先: `<docs/.../output.md>` または `work/<Agent名>/Issue-<識別子>/<artifact>.md`
- スキーマ: <H2 見出し列・表形式の列順を固定で記載>

## 4) 実行手順（順序固定）

1. <Step 1: 入力読み込みと検証>
2. <Step 2: 分析・生成>
3. <Step 3: 出力・自己点検>
4. <Step 4: 完了報告作成（§7 準拠）>

## 5) 品質原則（必ず守る）

- 捏造禁止 / 最小差分 / 検証実施 / 検証マーカー記載
- <Agent 固有の品質ルール>

## 6) セルフチェック（出力前に必ず確認）

- [ ] 出力スキーマの列順・列名が固定通りか
- [ ] 不明箇所が `TBD` で明示されているか（推論補完時は「Copilot推論」と明記）
- [ ] レビュー指摘を成果物に反映した場合、`hve/prompts.py` REVIEW_PROMPT 規定の証跡表を完了報告に記載したか
- [ ] `## Agent 固有の Skills 依存` セクションが空でないか（CI が検出する）

## 7) 完了条件

- 出力ファイルが指定パスに作成され、スキーマを満たしている
- 完了報告（PR body / `completion-report.md`）に検証結果と検証マーカーが記載されている
- レビュー指摘（あれば）に対する成果物反映証跡が記載されている

## 関連 / 参考

- `.github/agents/CONTRIBUTING.md` — frontmatter スキーマ
- `.github/scripts/validate-agents.py` — CI 検査内容（空 Skills 依存検出を含む）
- `hve/prompts.py` `REVIEW_PROMPT` — 敵対的レビュー時の証跡セクション仕様
