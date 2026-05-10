# Copilot 共通ルール

本ファイルは Copilot が最初に参照する **最上位の強制ルール（エントリーポイント）**。
詳細手順は各 Skill（`.github/skills/*/SKILL.md`）に委譲する。本ファイルが規範ルール、Skills が技術手順リファレンスであり、両者で正式ルールを構成する。なお Skills ファイルに移行過渡期の旧参照が残る場合があるが、本ファイルの記述が常に優先される。

---

## §0 最優先ルール（認知プライミング）

- **出力言語**: 出力は日本語。見出し＋箇条書き中心で簡潔に。
- **出力は最小限**: 長文は `work/` 配下（Skill work-artifacts-layout）。
- **変更は最小差分**: 無関係な整形・一括リファクタ・不要依存追加をしない。
- **捏造禁止**: ID/URL/固有名/数値/事実を根拠なく作らない。不明は `TBD` / `不明（要確認）` と明記する。
- **秘密情報禁止**: 鍵・トークン・個人情報・内部 URL 等を追加・出力しない。
- **推論補完時**: `TBD（推論: {根拠}）` + 「この回答はCopilot推論をしたものです。」と明記する。
- **task_scope=multi または context_size=large → 実装開始禁止**: plan.md + subissues.md のみ作成して終了する。
- **plan.md 冒頭5行にメタデータ必須**（Skill task-dag-planning §2.1.2）。欠落は CI で自動拒否。
- **最低1つの検証を実施**: テスト/ビルド/静的解析のいずれかを行い、できない場合は理由と代替を明記する。
  - **PR body 必須記載書式**（`auto-approve-and-merge.yml` の自動判定対象）: 以下のいずれかの形式で記載すること:
    1. HTML コメントマーカー: `<!-- validation-confirmed -->`（推奨。最も確実）
    2. 見出し: `## 検証` / `## 検証結果` / `## Validation` 等（行頭 `#` + 語）
    3. 箇条書き / 強調: `- 検証: <内容>` / `**検証**: <内容>`（行頭 + 語 + コロン）
  - 検証実施が困難な場合も「検証: 該当なし（理由: ...、代替: ...）」と記載すること。
- **ルート README.md 変更禁止**: `/README.md` を作成・変更してはならない。`README.md` のような裸パス表現は避け、ルート以外の README を指す必要がある場合は `infra/.../README.md` などの明示パスで記載する。
- **質問方針**：質問なしで進められる場合は質問しない。必要な質問は分類項目・重要度（最重要/高/中/低）付きで過不足なく行う。「最重要」「高」は回答を優先的に求め、「中」「低」は既定値で進行可能とする。Issue/PR body に `<!-- auto-context-review: true -->` が記載されている時は、コンテキストが十分な場合でも設計判断・技術選定・スコープの確認を目的として質問する。
- **推論許可**：「推論で進めてください」の意思表示を以降「**推論許可**」と呼ぶ。
- **書き込み失敗対策**：edit 後に read で空でないことを確認。空なら小チャンク（2,000〜5,000文字）に分割して再試行（最大3回）。
- **work/ および qa/ 書き込みルール（絶対）**：`work/` または `qa/` 配下へのファイル書き込みは Skill `work-artifacts-layout` §4.1 準拠。例外なし。
- **knowledge/ 書き込みルール（絶対）**：`knowledge/` 配下へのファイル書き込みも Skill `work-artifacts-layout` §4.1 準拠（削除→新規作成）。例外なし。
- **knowledge/ 同時更新防止（LOCK）**: `knowledge/` 本体ファイルへ LOCK 情報を埋め込んではならない。LOCK が必要な場合は `work/` 配下のロックファイル、または Issue ラベル等、`knowledge/` の「削除→新規作成」ルールと両立する方式を用いる。他の Agent により対象 D{NN} の LOCK が取得済みであることを検知した場合、後続 Agent は当該 `knowledge/` ファイルを **読み取り専用** とし、書き込みを中止して再実行に回す。
- **original-docs/ 読み取り専用（絶対）**: `original-docs/` 配下のファイルは全 Agent から **読み取り専用**。変更・削除・追記を禁止。

---

## §1 ワークフロー概要

Agent の標準作業フローは以下の 5 フェーズで構成される。各フェーズで参照すべき Skill を明示する。

```
[1. コンテキスト収集]
  - PR 連携: Skill: task-questionnaire（詳細）
  - 非 PR 連携: Skill: task-questionnaire（詳細）
        ↓
[2. 計画（DAG + 見積 + 分割判定）]
  - Skill: task-dag-planning
  - task_scope=multi または context_size=large → SPLIT_REQUIRED（実装禁止）
        ↓
[3. 実装]
  - work/ 構造: Skill: work-artifacts-layout
  - 大量出力: Skill: large-output-chunking
  - 安全ガード: Skill: harness-safety-guard
        ↓
[4. 検証]
  - Skill: harness-verification-loop（Build/Lint/Test/Security/Diff）
  - エラー発生時: Skill: harness-error-recovery
  - レビュー（ユーザー指定時のみ）: Skill: adversarial-review
        ↓
[5. PR]
  - 元 Issue リンク必須 → §7 参照
  - §7 に従い PR description を記載
```

初見のリポジトリの場合は先に **Skill: repo-onboarding-fast** を参照すること。

---

## §2 Skills ルーティング

Skill の参照先選定は **Skill `_routing`**（`.github/skills/_routing/SKILL.md`）を参照すること。
本体には強制ルール（§0, §3, §5-§10）を残し、ルーティング表は `_routing` Skill で管理する。

---

## §3 コアルール参照テーブル

本ファイルの §0 に記載されたコアルールと、対応する Skill の対応表。

| ルール | 詳細を持つ Skill |
|---|---|
| コンテキスト収集（PR連携 / 非PR連携） | `task-questionnaire` |
| plan.md メタデータ・分割判定 | `task-dag-planning` |
| 成果物パス・work/qa/ 構造 | `work-artifacts-layout` |
| 巨大出力分割 | `large-output-chunking` |
| 敵対的レビュー | `adversarial-review` |
| 検証ループ (Build/Lint/Test/Security/Diff) | `harness-verification-loop` |
| 安全ガード (破壊的操作検出) | `harness-safety-guard` |
| エラーリカバリ (3要素出力) | `harness-error-recovery` |
| リポジトリ初見オンボーディング | `repo-onboarding-fast` |

---

## §4 アプリケーション粒度の参照ルール（`docs/catalog/app-catalog.md` + §4）

詳細ルール（APP × サービス/エンティティ N:N、APP × 画面 1:1、成果物ファイル分割基準）: Skill `app-scope-resolution` §成果物ファイル分割基準 参照。

コード→要件→ADR トレーサビリティ（コードコメント・PR description・テストコードへの埋め込み形式）: Skill `knowledge-management` §コード→要件→ADR トレーサビリティ 参照。

---

## §5 Custom Agent との関係

Custom Agent（`.github/agents/*.agent.md`）は、本ファイルのルールを継承し、固有の追加ルールのみを記載する。

**優先順位（高 → 低）**:
1. **本ファイル（copilot-instructions.md）**（最優先・常に適用）
2. **Custom Agent のジョブ定義**（リポジトリ固有の方針）
3. **Skills**（技術リファレンス）

> 本ファイルの記述と Custom Agent の記述が矛盾する場合は本ファイルが優先される。
> SKILL.md と Custom Agent の記述が矛盾する場合は Custom Agent が優先される。
> `agent-common-preamble` Skill の共通ルールは、Agent 側で明示的にオーバーライドしない限り適用される（デフォルト継承モデル）。

**Skills 参照ルール（Custom Agent 向け）**:
- `.github/skills/` 配下の SKILL.md は、技術リファレンス（手順・コマンド・トラブルシューティング）を提供する。
- Custom Agent は、作業開始時に `agent-common-preamble` Skill を参照し、共通ルールを確認すること。
- Custom Agent 固有の追加 Skills は `## Agent 固有の Skills 依存` セクションに明示する。
- SKILL.md の情報を採用しない場合は、Custom Agent 側でその理由を明記すること（Non-goals 等で）。

**original-docs/ に関するルール（全 Agent 必須）**:
- 読み取り専用ルール: §0 参照（変更・削除・追記禁止）
- `original-docs/` のファイルを knowledge/ に取り込む作業は `KnowledgeManager` Agent が担当
- 他の Agent は、ユースケースに応じて以下のいずれかの参照方式を選択できる:
  - **直接参照**: `original-docs/` を直接読み取る（横断分析・質問票作成・早期フィードバック等で有効）
  - **knowledge/ 経由参照**: `KnowledgeManager` が生成した `knowledge/D01〜D21-*.md` を参照
  - **ハイブリッド**: 両方を参照
- どの参照方式を採用したかは Agent 仕様の `## 入力` セクションに明記すること

---

## §6 直列/並列の判断と共有（衝突を避ける）

詳細判断基準・共有方法: Skill `task-dag-planning` §直列/並列の判断と共有 参照。

---

## §7 PRに必ず書く（短くてよい）

- **元 Issue リンク（必須）**: PR の起点となった Issue 番号を `Fixes #N` / `Closes #N` / `Resolves #N` で記載する（分割モード・PROCEED モード問わず全 PR に適用。Issue 番号が不明な場合は `<!-- parent-issue: #N -->` を記載）。
- **PR body 更新時の保持義務（必須）**: PR body を更新する場合、既存の `Fixes #N` / `Closes #N` / `Resolves #N` および `<!-- parent-issue: #N -->` を **絶対に削除しないこと**。PR body を全置換する場合は、元の body からこれらを抽出して新しい body の先頭に再挿入すること。
- PR body 必須セクション: **目的** / **変更点** / **影響範囲** / **検証結果**（§0 書式準拠）/ **既知の制約** / **次にやるSub**（残作業）

---

## §8 出力品質 (Observation Quality)

全 Agent の成果物に `status` / `summary` / `next_actions` / `artifacts` の4要素を含める。テンプレート詳細: Skill `work-artifacts-layout` §成果物サマリーテンプレート 参照。§7 の「目的/変更点/影響範囲/検証結果/既知の制約/次にやるSub」と統合して PR description 内に記載する。

---

## §9 差分品質評価 (Diff Quality Assessment)

PR 提出前に実施する。詳細手順（`git diff --stat` によるスコープ確認・無関係変更検出・`verification-report.md` への記録）: Skill `harness-verification-loop` §差分品質評価 参照。

---

## §10 例外（下位ディレクトリ固有ルールを置く場合）

- 置くのは「そのディレクトリ固有の追加ルール」だけ。
- 必ず「ルート copilot-instructions.md を継承し、追加/上書き点のみ記載」と明記する。
