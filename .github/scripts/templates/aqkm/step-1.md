{root_ref}
## 目的
`qa/` フォルダーの質問ファイルを knowledge/ ドキュメント（D01〜D21）を生成・管理し、`knowledge/business-requirement-document-status.md` を更新する。QA マッピングが存在する各 D クラスについて `knowledge/D{NN}-<文書名>.md` を個別に生成する（0〜21 個可変。マッピングがない D クラスはファイルを生成しない）。

## Custom Agent
`QA-KnowledgeManager`

## 処理フロー
QA-KnowledgeManager Agent の定義（`.github/agents/QA-KnowledgeManager.agent.md`）に従い、以下の 9 ステップを 1 セッション内で順次処理する。

1. **入力ファイル収集** — スコープに従い `qa/*.md` を収集し、メタデータを抽出する
2. **マスターリスト読み込み** — `template/business-requirement-document-master-list.md` を読み込む
3. **質問項目の抽出・正規化** — 各ファイルの質問テーブルをパースし、質問 ID を生成する
4. **D01〜D21 マッピング** — Primary D / Contributing D を判定する（`.github/instructions/knowledge-management.instructions.md` の §2 マッピングルールに従う）
5. **状態判定** — Confirmed / Tentative / Unknown を判定する（§3 状態判定ルールに従う）
6. **カバレッジ分析** — D クラス別のカバレッジと不足項目を分析する（§5 カバレッジ分析ルールに従う）
7. **status.md 生成** — `knowledge/business-requirement-document-status.md` を §4 テンプレートに従い生成・更新する
7.5. **knowledge/ 文書生成** — QA マッピングが存在する各 D クラスについて `knowledge/D{NN}-<文書名>.md` を §7 テンプレートに従い個別生成する（マッピング 0 件の D クラスはスキップ）
8. **敵対的レビュー**（オプション — `adversarial-review` ラベルまたは `<!-- adversarial-review: true -->` が指定された場合のみ実行）— AGENTS.md §7 に従い 5 軸（要件充足性/技術的正確性/整合性/非機能品質/捏造検出）で成果物をレビューし、Critical 指摘を修正する

## 実行パラメータ

| パラメータ | 値 |
|-----------|---|
| スコープ | `{aqkm_scope}` |
| force_refresh | `{aqkm_force_refresh}` |
{aqkm_target_files_section}

## 入力
- `qa/*.md`（スコープに応じてフィルタリング）
- `template/business-requirement-document-master-list.md`
- `.github/instructions/knowledge-management.instructions.md`

## 出力
- `knowledge/business-requirement-document-status.md`（生成・更新）
- `knowledge/D{NN}-<文書名>.md`（QA マッピングが存在する D クラス数だけ個別生成）

## 依存
- なし（最初に実行）

## 完了条件
- `knowledge/business-requirement-document-status.md` が生成・更新されている
- QA マッピングが存在する各 D クラスについて `knowledge/D{NN}-<文書名>.md` が生成されている
- 敵対的レビューで Critical 指摘が 0 件
- 完了時に自身に `aqkm:done` ラベルを付与すること{additional_section}
