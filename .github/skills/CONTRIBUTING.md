# Skill 開発コントリビューションガイド

> **対象**: 本リポジトリ（`.github/skills/`）に新規 Skill を追加・変更する開発者向けガイド。
> **優先順位**: `.github/copilot-instructions.md` > Custom Agent > Skills（本ファイル）。本ガイドと上位ファイルが矛盾する場合は上位が優先される。

---

## 目次

1. [Skill 作成チェックリスト](#1-skill-作成チェックリスト)
2. [description 言語方針](#2-description-言語方針)
3. [description 文字数の推奨](#3-description-文字数の推奨)
4. [ディレクトリ構造テンプレート](#4-ディレクトリ構造テンプレート)
5. [Sub-skill パターンの使用基準](#5-sub-skill-パターンの使用基準)
6. [description 統一フォーマット](#6-description-統一フォーマット)
7. [`## Related Skills` セクションの記載基準](#7-related-skills-セクションの記載基準)
8. [入出力例セクションの推奨](#8-入出力例セクションの推奨)
9. [SKILL.md テンプレート](#9-skillmd-テンプレート)
10. [既存パターンとの整合性チェック](#10-既存パターンとの整合性チェック)

---

## 1. Skill 作成チェックリスト

### 必須項目

- [ ] **フォルダ名は kebab-case**（例: `dataflow-design-guide`, `deploy-model`）。プロダクト名を含む場合はプロダクト名の表記規則に従う（例: `microsoft-foundry` はプロダクト名のまま）
- [ ] **`SKILL.md` に YAML frontmatter** を記載する（`name`, `description`, `metadata.version` の3フィールドは必須）
- [ ] **`description` 全体を GitHub Copilot / VS Code Agent Skills の現行仕様に合わせる**（[§3](#3-description-文字数の推奨), [§6](#6-description-統一フォーマット) 参照）:
  - `description` 全体は 1〜1024 文字
  - 冒頭サマリーは簡潔にし、200 文字以下を推奨
  - `USE FOR:` / `DO NOT USE FOR:` / `WHEN:` の既存フォーマットを原則使う
  - 既存互換の 1 行 `Use when:` 形式も不正扱いしない
- [ ] **`## Non-goals（このスキルの範囲外）` セクション** を SKILL.md に記載する
- [ ] **詳細手順が多い場合や条件別の補足が必要な場合は `references/` への分離を推奨する**（SKILL.md は概要・ルーティング・必要な参照先を中心に簡潔に保つ）
- [ ] **`.github/skills/_routing/README.md` のルーティングテーブルに追加する**（既存カテゴリへの追加の場合は該当カテゴリテーブルを更新する）
- [ ] **変更後に `python3 .github/scripts/validate-skill-routing.py` を実行する**（ルーティング整合・重複・frontmatter 必須項目の自動検証）

### 推奨項目

- [ ] **`## Related Skills` セクション**（依存先 Skill が 3 件以上の場合に追記を推奨）
- [ ] **`## 入出力例` セクション**（具体的な入力 → 出力の例を 1 件以上）
- [ ] **`.github/skills/_evals/` へのテストケース追加**（Eval フレームワーク導入済みの場合）

### frontmatter スキーマ（確定）

- **必須**
  - `name`（1〜64 文字）
  - `description`（全体で 1〜1024 文字）
  - `metadata.version`（SemVer: `MAJOR.MINOR.PATCH`、例: `1.0.0`）
- **推奨**
  - `category`
  - `applies_to`
- **廃止**
  - `metadata.version` なしの旧 frontmatter 形式は受け入れない（互換 fallback なし）

---

## 2. description 言語方針

Skill `agent-common-preamble` の出力言語ルールに準拠し、
以下の方針を適用する。

| 項目 | 言語 | 理由 |
|------|------|------|
| サマリー（1行目） | **日本語** | §0 準拠。Agent/Copilot が日本語コンテキストで読む |
| `USE FOR:` の値 | **英語**（許容） | トリガーキーワードは英語の方がマッチ精度が安定することがある |
| `DO NOT USE FOR:` の値 | **英語**（許容） | 同上 |
| `WHEN:` の値 | **日本語** | ユーザーの発話・コンテキストは日本語が主体 |
| SKILL.md 本文 | **日本語** | §0 準拠 |

> ⚠️ **プラットフォーム注意**: `USE FOR` / `DO NOT USE FOR` の英語キーワードは GitHub Copilot 向けの説明補助として扱う。精度保証のために同義語を大量列挙するのではなく、用途・除外・発動条件を少数の明確な語で表す。

---

## 3. description 文字数の推奨

- **description 全体**: GitHub Copilot / VS Code Agent Skills の現行公式仕様では **1〜1024 文字**。この範囲は `USE FOR` / `DO NOT USE FOR` / `WHEN` 等を含む `description` 全体に適用される
- **サマリー部分（冒頭の用途説明）**: **200 文字以下** を推奨する。これは読みやすさの目安であり、受け入れ可否の hard gate ではない
- `USE FOR` / `DO NOT USE FOR` / `WHEN` は、少数の明確なキーワードと条件で十分。5〜15 個、3〜8 個、3〜10 個といった個数目安を義務として扱わない
- 既存 Skill の `description` が 1024 文字以内で用途・除外・発動条件を十分に伝えている場合、同義語を増やすためだけに書き換えない

---

## 4. ディレクトリ構造テンプレート

既存 Skill は `.github/skills/<skill-name>/` 直下、または既存カテゴリ配下に置く。下図の `<category>/` はカテゴリ配下へ配置する場合だけ付ける。

```
.github/skills/<category>/<skill-name>/
├── SKILL.md           ← 概要・ルーティング・入出力例（必須）
├── references/        ← 詳細手順・ルールリファレンス（条件別に必要な場合）
│   ├── detail-1.md
│   └── detail-2.md
├── scripts/           ← 実行スクリプト（必要な場合）
├── examples/          ← コード例・具体例（必要な場合）
└── assets/            ← テンプレート・フォーマット定義（必要な場合）
```

### 現行の配置例

| カテゴリ | 用途 | 例 |
|---------|------|-----|
| `.github/skills/` 直下 | 計画・コンテキスト収集・設計ガイド等 | `task-dag-planning`, `dataflow-design-guide` |
| `harness/` | 検証・安全ガード・エラーリカバリ | `harness-verification-loop`, `adversarial-review` |
| `output/` | 出力フォーマット・分割・可視化 | `large-output-chunking`, `docs-output-format` |
| `azure-skills/` | HVE の Azure デプロイ・検証契約 | `azure-cli-deploy-scripts`, `azure-region-policy`, `azure-ac-verification` |
| `cicd/` | GitHub Actions CI/CD | `github-actions-cicd` |
| `testing/` | テスト戦略・テンプレート | `requirements-conformance-measurement`, `tdd-red-green-reality` |

Skill の追加は、HVE 固有契約または本リポジトリの既存配布要件を文書化・運用する必要がある場合に限定する。汎用 SE 教材や単体 Tips は再同梱しない。外部の独立版 Skill や配布 kit 由来の Skill を参照する場合は、元の name/path/配置規約を保持し、リポジトリ内へ包括的な新 Skill として再定義しない。

> 既存カテゴリに当てはまらない場合は、新カテゴリを作成して
> `.github/skills/_routing/README.md` のルーティングテーブルに追加する。

### カテゴリ外ディレクトリ（特別用途）

- `_routing/`: **カテゴリ外（ルーティング定義専用）**。
  `README.md` でカテゴリ横断の参照先表を管理する。
- `_evals/`: **カテゴリ外（評価専用）**。
  Eval ケース格納用で、`SKILL.md` は不要。

> `_routing/` と `_evals/` は Skill 本体ではなく、登録・評価用の補助ディレクトリである。

---

## 5. Sub-skill パターンの使用基準

### 使うべき場合 ✅

**ユーザーの意図によって処理フローが分岐する場合**に Sub-skill パターンを採用する。

```
~/.agents/skills/microsoft-foundry/models/deploy-model/
├── SKILL.md           ← ルーター（intent detection → Sub-skill へのルーティング）
├── preset/
│   └── SKILL.md       ← クイックデプロイ
├── customize/
│   └── SKILL.md       ← フル設定デプロイ
└── capacity/
    └── SKILL.md       ← キャパシティ探索
```

外部 Skill の例: `deploy-model`（`preset` / `customize` / `capacity` の 3 モード）。実際の構成は導入済みの外部 Skill の版で確認し、リポジトリへ複製しない。

### 使わない場合 ❌

**連続実行フロー**（ステップが固定順序で実行される）は分割しない。

```
# NG: task-dag-planning の §1 → §2 → §3 を Sub-skill に分割しない
# → 固定フローなので 1 つの SKILL.md に手順として記載する
```

### 判断基準まとめ

| 条件 | パターン |
|------|---------|
| ユーザーの意図・入力によって分岐がある | **Sub-skill パターンを使う** |
| 連続実行・固定順序のフロー | **1 つの SKILL.md に手順を記載** |
| Skill が 100 行を超えて肥大化しているが分岐なし | **`references/` への詳細分離を検討**（100 行や 500 行などの行数は参考目安であり hard gate ではない） |

---

## 6. description 統一フォーマット

新規 Skill の `description` は、原則として以下の既存フォーマットで記述する。ただし、既存互換の 1 行 `Use when:` 形式も有効な説明として扱い、形式だけを理由に不正としない。

### フォーマット（YAML ブロックスカラー形式）

```yaml
description: >
  [簡潔な日本語サマリー。1文で Skill の目的を説明する。]
  USE FOR: [英語トリガーキーワード1], [英語トリガーキーワード2], [英語トリガーキーワード3].
  DO NOT USE FOR: [除外条件1（英語）], [除外条件2（英語）].
  WHEN: [日本語での発動条件1]、[日本語での発動条件2]。
```

### 記述ガイドライン

| セクション | 記述内容 | 目安 |
|-----------|---------|------|
| サマリー | Skill の目的を 1 文で説明 | 200 文字以下を推奨 |
| `USE FOR:` | このスキルを発動すべき代表キーワード（英語、コンマ区切り） | 少数の明確な語で十分 |
| `DO NOT USE FOR:` | このスキルを使わないべき代表ケース（誤発動防止） | 必要最小限 |
| `WHEN:` | 日本語でのトリガー発動条件（読点区切り） | 主要条件のみ |

> 個数や行数は読みやすさの参考値であり、validator の hard gate にしない。特に、同義語を大量に並べて 1024 文字上限へ近づけるより、用途・除外・WHEN を短く明確に書くことを優先する。

### 記述例

```yaml
description: >
  knowledge/ 配下の確定済みドメイン知識ドキュメントを参照する。
  USE FOR: checking business rules, verifying glossary definitions, reviewing data model specifications.
  DO NOT USE FOR: creating or updating knowledge files (use knowledge-management).
  WHEN: タスク実行中に業務要件を確認したい、用語定義やデータモデル仕様を確認したい。
```

既存互換の 1 行説明も、用途が明確で 1024 文字以内であれば維持してよい。

```yaml
description: "Use when: generated application design or development must select, validate, cite, and trace APP-specific requirements without loading every requirement document."
```

---

## 7. `## Related Skills` セクションの記載基準

### 記載すべき場合

- 本 Skill が **他の Skill を前提・依存関係として明示したい** 場合
- **依存先 Skill が 3 件以上**ある場合（推奨）
- 誤って本 Skill が使われることを防ぐため **代替 Skill を案内したい** 場合

### フォーマット

```markdown
## Related Skills

| Skill | 関係 | 用途 |
|-------|------|------|
| `task-questionnaire` | 先行 | コンテキスト収集（本スキル実行前に使う） |
| `work-artifacts-layout` | 依存 | 成果物パスの設計 |
| `harness-verification-loop` | 後続 | 検証フェーズの実行 |
```

### 関係の種類

| 関係 | 意味 |
|------|------|
| `先行` | 本 Skill の実行前に使うべき Skill |
| `依存` | 本 Skill が内部で参照・呼び出す Skill |
| `後続` | 本 Skill の完了後に使うべき Skill |
| `代替` | 本 Skill の代わりに使うべき Skill（Non-goals との対応） |

---

## 8. 入出力例セクションの推奨

SKILL.md に `## 入出力例` セクションを設けることを**推奨**する。具体例があることで Agent が Skill の期待する動作を理解しやすくなる。

### フォーマット

````markdown
## 入出力例

### 例 1: [ケース名]

**入力（ユーザーの発話 / Agent へのリクエスト）:**
```
[具体的な入力例]
```

**出力（期待する成果物 / アクション）:**
```
[具体的な出力例]
```
````

### 記載ガイドライン

- **最低 1 件**の入出力例を記載する（推奨）
- **正常ケース**と**スコープ境界ケース（Non-goals に近いケース）**の 2 件があると理想的
- 入力はユーザーの実際の発話に近い形で記述する

---

## 9. SKILL.md テンプレート

新規 Skill を作成する際は、以下のテンプレートをコピーして使用する。

````markdown
---
name: <skill-name>
description: >
  [簡潔な日本語サマリー。]
  USE FOR: [英語キーワード1], [英語キーワード2], [英語キーワード3].
  DO NOT USE FOR: [除外条件1（英語）], [除外条件2（英語）].
  WHEN: [日本語での発動条件1]、[日本語での発動条件2]。
metadata:
  origin: user
  version: "1.0.0"
---

# <Skill 名>

## 目的

[このスキルが解決する問題・提供する価値を 3 行以内で説明する。]

## Non-goals（このスキルの範囲外）

- **[範囲外の責務1]** — [代替 Skill があれば記載する]
- **[範囲外の責務2]** — [代替 Skill があれば記載する]

## 手順 または 使用方法

[手順が短い場合はここに直接記載する。長い場合や条件別の詳細が必要な場合は `references/` に分離して、ここには必要な参照先のみを記載する。]

1. [ステップ1]
2. [ステップ2]
3. [ステップ3]

または、詳細な手順は references/ を参照:

| ファイル | 内容 |
|---------|------|
| `references/detail-1.md` | [説明] |
| `references/detail-2.md` | [説明] |

## Related Skills

> ⚠️ 依存先が 3 件未満の場合は本セクションを省略してよい。

| Skill | 関係 | 用途 |
|-------|------|------|
| `[skill-name]` | [先行/依存/後続/代替] | [用途の説明] |

## 入出力例

### 例 1: [ケース名]

**入力:**
```
[ユーザーの発話・リクエスト例]
```

**出力:**
```
[期待する成果物・アクション例]
```
````

---

## 10. 既存パターンとの整合性チェック

新規 Skill を追加する前に、以下の既存パターンとの整合性を確認する。

### 10.1 優先順位

```
.github/copilot-instructions.md  ← 最優先（常に適用）
        ↓
Custom Agent（.github/prompts/*.prompt.md）
        ↓
Skills（.github/skills/**/SKILL.md）← 本ガイドが対象とする層
```

- Skill の記述が `.github/copilot-instructions.md` と矛盾する場合は
  `.github/copilot-instructions.md` が優先される
- Custom Agent 固有の指示が Skill と矛盾する場合は Custom Agent が優先される

### 10.2 agent-common-preamble のデフォルト継承モデル

- 全 Custom Agent は作業開始時に `agent-common-preamble` Skill を参照する
- 新規 Skill が全 Agent に適用される共通ルールを含む場合は、`agent-common-preamble` または `.github/skills/_routing/README.md` への追加を検討する
- `agent-common-preamble` を更新する場合は、全 Agent の挙動に影響することを考慮して慎重に変更する

### 10.3 work/ および qa/ 配下への書き込みルール

`work-artifacts-layout` Skill §4.1 のルールに従い、`work/` または `qa/` 配下へのファイル書き込みは **削除 → 新規作成** パターンを使う。既存ファイルへの追記ではなく、必ず全体を再生成する。

### 10.4 ルーティングテーブルへの追加

新規 Skill を追加したら、必ず `.github/skills/_routing/README.md` のルーティングテーブルに追記する。

```markdown
| フェーズ / トリガー | 参照 Skill | パス | 説明 |
|---|---|---|---|
| [発動条件] | `<skill-name>` | `.github/skills/<category>/<skill-name>/SKILL.md` | [1行説明] |
```

---

## 成果物サマリー

- **status**: ガイドとして参照可能
- **summary**: 現行のルーティング表と同梱契約を確認して Skill を作成・保守する
- **next_actions**: 新規 Skill を追加する場合は §1 チェックリストを起点とし、§9 テンプレートを使用する
- **artifacts**: `.github/skills/CONTRIBUTING.md`（本ファイル）
