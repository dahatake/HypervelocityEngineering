# Skill 開発コントリビューションガイド

> **対象**: 本リポジトリ（`.github/skills/`）に新規 Skill を追加・変更する開発者向けガイド。
> **優先順位**: `copilot-instructions.md` > Custom Agent > Skills（本ファイル）。本ガイドと上位ファイルが矛盾する場合は上位が優先される。

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

- [ ] **フォルダ名は kebab-case**（例: `task-dag-planning`, `deploy-model`）。プロダクト名を含む場合はプロダクト名の表記規則に従う（例: `microsoft-foundry` はプロダクト名のまま）
- [ ] **`SKILL.md` に YAML frontmatter** を記載する（`name`, `description`, `metadata.version` の3フィールドは必須）
- [ ] **`description` に以下を含む**（[§6](#6-description-統一フォーマット) 参照）:
  - 200文字以下の日本語サマリー
  - `USE FOR:` トリガーキーワード（英語）
  - `DO NOT USE FOR:` 除外条件（英語）
  - `WHEN:` 日本語での発動条件
- [ ] **`## Non-goals（このスキルの範囲外）` セクション** を SKILL.md に記載する
- [ ] **詳細手順が多い場合は `references/` への分離を推奨する**（SKILL.md は概要・ルーティング・入出力例を中心に簡潔に保つ）
- [ ] **`copilot-instructions.md` §2 ルーティングテーブルに追加する**（既存カテゴリへの追加の場合は §2 の該当カテゴリテーブルを更新する）

### 推奨項目

- [ ] **`## Related Skills` セクション**（依存先 Skill が 3 件以上の場合に追記を推奨）
- [ ] **`## 入出力例` セクション**（具体的な入力 → 出力の例を 1 件以上）
- [ ] **`.github/skills/_evals/` へのテストケース追加**（Eval フレームワーク導入済みの場合）

---

## 2. description 言語方針

`copilot-instructions.md` §0「出力は日本語」ルールに準拠し、以下の方針を適用する。

| 項目 | 言語 | 理由 |
|------|------|------|
| サマリー（1行目） | **日本語** | §0 準拠。Agent/Copilot が日本語コンテキストで読む |
| `USE FOR:` の値 | **英語**（許容） | トリガーキーワードは英語の方がマッチ精度が安定することがある |
| `DO NOT USE FOR:` の値 | **英語**（許容） | 同上 |
| `WHEN:` の値 | **日本語** | ユーザーの発話・コンテキストは日本語が主体 |
| SKILL.md 本文 | **日本語** | §0 準拠 |

> ⚠️ **プラットフォーム注意**: `USE FOR` / `DO NOT USE FOR` の英語キーワードが GitHub Copilot において Anthropic Claude と同一の精度でトリガーとして動作するかは未確認。現時点では「推奨」として記載し、断定しない。

---

## 3. description 文字数の推奨

- **サマリー部分（1行目）**: **200文字以下** を推奨する
- `USE FOR` / `DO NOT USE FOR` / `WHEN` を含む `description` 全体の実質的な文字数上限は **未確定**
  - GitHub Copilot のプラットフォーム固有の制限が判明次第、本ガイドを更新する
  - 参考: Anthropic ガイドでは 1024 文字以下を推奨（ただし GitHub Copilot では未検証）
- 既存の実例として `task-dag-planning`（約 300 文字）、`deploy-model`（約 500 文字）が実績あり

---

## 4. ディレクトリ構造テンプレート

```
.github/skills/<category>/<skill-name>/
├── SKILL.md           ← 概要・ルーティング・入出力例（必須）
├── references/        ← 詳細手順・ルールリファレンス（推奨）
│   ├── detail-1.md
│   └── detail-2.md
├── scripts/           ← 実行スクリプト（必要な場合）
├── examples/          ← コード例・具体例（必要な場合）
└── assets/            ← テンプレート・フォーマット定義（必要な場合）
```

### カテゴリ一覧（既存 7 カテゴリ）

| カテゴリ | 用途 | 例 |
|---------|------|-----|
| `planning/` | 計画・コンテキスト収集・設計ガイド | `task-dag-planning`, `batch-design-guide` |
| `harness/` | 検証・安全ガード・エラーリカバリ | `harness-verification-loop`, `adversarial-review` |
| `output/` | 出力フォーマット・分割・可視化 | `large-output-chunking`, `svg-renderer` |
| `azure-platform/` | Azure サービス固有のリファレンス | `azure-deploy`, `microsoft-foundry` |
| `cicd/` | GitHub Actions CI/CD | `github-actions-cicd` |
| `observability/` | 監視・計装 | `appinsights-instrumentation` |
| `testing/` | テスト戦略・テンプレート | `test-strategy-template` |

> 既存カテゴリに当てはまらない場合は、新カテゴリを作成して `copilot-instructions.md` §2 のルーティングテーブルに追加する。

---

## 5. Sub-skill パターンの使用基準

### 使うべき場合 ✅

**ユーザーの意図によって処理フローが分岐する場合**に Sub-skill パターンを採用する。

```
.github/skills/azure-platform/microsoft-foundry/models/deploy-model/
├── SKILL.md           ← ルーター（intent detection → Sub-skill へのルーティング）
├── preset/
│   └── SKILL.md       ← クイックデプロイ
├── customize/
│   └── SKILL.md       ← フル設定デプロイ
└── capacity/
    └── SKILL.md       ← キャパシティ探索
```

実例: `deploy-model`（`preset` / `customize` / `capacity` の 3 モード）

### 使わない場合 ❌

**連続実行フロー**（ステップが固定順序で実行される）は分割しない。

```
# NG: task-dag-planning の §2.1 → §2.2 → §2.3 を Sub-skill に分割しない
# → 固定フローなので 1 つの SKILL.md に手順として記載する
```

### 判断基準まとめ

| 条件 | パターン |
|------|---------|
| ユーザーの意図・入力によって分岐がある | **Sub-skill パターンを使う** |
| 連続実行・固定順序のフロー | **1 つの SKILL.md に手順を記載** |
| Skill が 100 行を超えて肥大化しているが分岐なし | **`references/` に詳細を分離** |

---

## 6. description 統一フォーマット

新規 Skill の `description` は以下のフォーマットに従って記述する。

### フォーマット（YAML ブロックスカラー形式）

```yaml
description: >
  [200文字以下の日本語サマリー。1文で Skill の目的を説明する。]
  USE FOR: [英語トリガーキーワード1], [英語トリガーキーワード2], [英語トリガーキーワード3], ...
  DO NOT USE FOR: [除外条件1（英語）], [除外条件2（英語）], ...
  WHEN: [日本語での発動条件1]、[日本語での発動条件2]、[日本語での発動条件3]。
```

### 記述ガイドライン

| セクション | 記述内容 | 文字数目安 |
|-----------|---------|-----------|
| サマリー | Skill の目的を 1 文で説明 | 200 文字以下 |
| `USE FOR:` | このスキルを発動すべきキーワード（英語、コンマ区切り） | 5〜15 個程度 |
| `DO NOT USE FOR:` | このスキルを使わないべきケース（誤発動防止） | 3〜8 個程度 |
| `WHEN:` | 日本語でのトリガー発動条件（読点区切り） | 3〜10 個程度 |

### 記述例

```yaml
description: >
  データモデルと物理テーブルのマッピングを記録するデータカタログを生成する。
  USE FOR: data catalog, entity mapping, table definition, ER diagram generation,
  data model documentation, physical table design, entity relationship.
  DO NOT USE FOR: API design (use microservice-design-guide), batch job design
  (use batch-design-guide), infrastructure deployment (use azure-deploy).
  WHEN: データカタログを生成したい、エンティティとテーブルのマッピングを整理したい、
  ER 図を作成したい、物理テーブル設計を文書化したい。
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
  [200文字以下の日本語サマリー。]
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

[手順が短い場合はここに直接記載する。長い場合は `references/` に分離して、ここには索引のみを記載する。]

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

### 10.1 優先順位（`copilot-instructions.md` §5）

```
copilot-instructions.md  ← 最優先（常に適用）
        ↓
Custom Agent（.github/agents/*.agent.md）
        ↓
Skills（.github/skills/*/SKILL.md）← 本ガイドが対象とする層
```

- Skill の記述が `copilot-instructions.md` と矛盾する場合は `copilot-instructions.md` が優先される
- Custom Agent 固有の指示が Skill と矛盾する場合は Custom Agent が優先される

### 10.2 agent-common-preamble のデフォルト継承モデル

- 全 Custom Agent は作業開始時に `agent-common-preamble` Skill を参照する
- 新規 Skill が全 Agent に適用される共通ルールを含む場合は、`agent-common-preamble` または `copilot-instructions.md` §2 ルーティングテーブルへの追加を検討する
- `agent-common-preamble` を更新する場合は、全 Agent の挙動に影響することを考慮して慎重に変更する

### 10.3 work/ および qa/ 配下への書き込みルール

`work-artifacts-layout` Skill §4.1 のルールに従い、`work/` または `qa/` 配下へのファイル書き込みは **削除 → 新規作成** パターンを使う。既存ファイルへの追記ではなく、必ず全体を再生成する。

### 10.4 ルーティングテーブルへの追加

新規 Skill を追加したら、必ず `copilot-instructions.md` §2 のルーティングテーブルに追記する。

```markdown
| フェーズ / トリガー | 参照 Skill | パス | 説明 |
|---|---|---|---|
| [発動条件] | `<skill-name>` | `.github/skills/<category>/<skill-name>/SKILL.md` | [1行説明] |
```

---

## 成果物サマリー

- **status**: ガイドとして参照可能
- **summary**: 新規 Skill 開発者が本ガイドに従うことで、既存 47 Skill と整合性のある Skill を作成できる
- **next_actions**: 新規 Skill を追加する場合は §1 チェックリストを起点とし、§9 テンプレートを使用する
- **artifacts**: `.github/skills/CONTRIBUTING.md`（本ファイル）
