---
name: _template
description: |
  全 Agent 共通の構造テンプレート。新規 Agent 作成時または既存 Agent の構造統一時に
  本ファイルをコピーして使用する。USE FOR: agent file scaffolding, consistency check.
  DO NOT USE FOR: 実行可能な Agent 定義（Front matter の name に `_` 接頭辞があるため
  ディスパッチ対象外）。WHEN: 新規 Agent 作成、既存 Agent の構造統一。
tools: []
metadata:
  origin: template
  version: 1.0.0
  template_only: true
---

> 共通行動規約は `.github/copilot-instructions.md` および Skill `agent-common-preamble` を継承する。
> Agent 固有 Skills 依存は本ファイル `## Agent 固有の Skills 依存` セクションに明示する。

# {Agent-Name}

`<Agent の役割を 1-2 文で簡潔に>` を実施する。

## Agent 固有の Skills 依存

- `task-dag-planning`: タスク分割判定（必須）
- `work-artifacts-layout`: work/ 構造管理（必須）
- `task-questionnaire`: コンテキスト収集（QA 連携時のみ）
- `harness-verification-loop`: 検証ループ（実装系のみ）
- `adversarial-review`: 敵対的レビュー（成果物品質確認時のみ）
- `<追加 Skill>`

## 1) 目的

- `<Agent の存在意義を 1-3 行>`

### Non-goals（対象外）

- `<本 Agent が扱わない範囲を明示。他 Agent への委譲先も記載>`

## 2) 入力

### 必読ファイル

| # | ファイル | 用途 |
|---|---|---|
| 1 | `<path>` | `<どのセクションを何のために参照するか>` |

### 推奨ファイル（任意）

| # | ファイル | 用途 |
|---|---|---|

### qa/ 参照（QA Phase 0 出力の利用）

- **対象 QA ファイル**: `qa/{run_id}-{step_id}-pre-execution-qa.md`（Phase 0 で生成された事前質問票）
- **参照方法**: HVE Auto-QA が `pre_qa_context` としてプロンプト先頭に注入するため、Agent は **明示的に読み込まなくても回答内容は受け取る**
- **追加読み込み**: 上記注入で不足する場合（特定の質問 ID への参照等）は、`qa/` ディレクトリを直接読み取ること
- **トレース義務**: 主タスク成果物に QA 回答を反映した箇所は、後述「## QA 回答の反映状況」に明示する

### knowledge/ 参照（業務コンテキスト）

- 関連する D{NN}: `<該当する knowledge/D{NN}-*.md を列挙、該当なしは "該当なし">`

## 3) 出力先

- 主成果物: `<path/to/output.md>`
- `{WORK}`: `work/<Agent-Name>/Issue-<識別子>/`
- 分割時のみ: `{WORK}plan.md`, `{WORK}subissues.md`

## 4) 実行手順

1. 必読ファイル検証（Skill `input-file-validation` 準拠）
2. `task-dag-planning` で分割判定（SPLIT_REQUIRED なら停止、`{WORK}subissues.md` 作成）
3. PROCEED の場合のみ実装に進む
4. 成果物作成
5. 検証（`harness-verification-loop`）
6. 完了報告（PR body / completion-report.md に「## QA 回答の反映状況」を含める）

## 5) 出力フォーマット

`<成果物の必須セクション・章立てを定義。テーブル形式推奨>`

## 6) 完了条件（DoD）

- [ ] 必読ファイル全て存在し読了
- [ ] 主成果物作成完了
- [ ] 検証コマンド PASS
- [ ] PR body / completion-report.md に「## QA 回答の反映状況」セクション記載
- [ ] PR body / completion-report.md に「## 成果物サマリー」（status / summary / next_actions / artifacts）記載

## 7) QA 回答の反映状況（成果物に必ず追記する）

主タスク完了時、Agent は以下のセクションを PR body または `completion-report.md` に追記すること：

```markdown
## QA 回答の反映状況

| 質問 ID | 質問の要約 | ユーザー回答 | 採用/不採用 | 反映先ファイル | 補足 |
|---|---|---|---|---|---|
| Q1 | <要約> | <回答> | 採用 | docs/foo.md#L<行> | <理由> |
| Q2 | <要約> | <回答> | 不採用 | - | <不採用理由> |
```

- Phase 0 で QA が無かった場合は「該当なし（Pre-QA 未実行）」と明記する
- 全 QA 回答に対して反映状況を必ず記載する（捏造禁止）

## 8) 禁止事項

- 根拠なき推測・捏造
- 必読ファイル不在時に「TBD」記載のまま進行（Skill `input-file-validation` 準拠）
- `qa/`, `knowledge/`, `original-docs/` への破壊的書き込み（読み取り専用）
- `<Agent 固有の禁止項目>`

## 9) 成果物サマリー（PR body / completion-report.md 必須）

```
## 成果物サマリー
- status:       [成功/失敗/部分完了]
- summary:      [何を行い何が変わったか（3行以内）]
- next_actions: [後続で必要な作業（あれば Agent 名を推奨付き）]
- artifacts:    [生成/変更したファイルの一覧]
```
