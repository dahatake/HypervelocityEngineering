{root_ref}
## 目的
`qa/` フォルダーの質問ファイルを D01〜D21 に分類し、`work/business-requirement-document-status.md` を生成・更新する。

## Custom Agent
`QA-RequirementClassifier`

## 処理フロー
QA-RequirementClassifier Agent の定義（`.github/agents/QA-RequirementClassifier.agent.md`）に従い、以下の 8 ステップを 1 セッション内で順次処理する。

1. **入力ファイル収集** — スコープに従い `qa/*.md` を収集し、メタデータを抽出する
2. **マスターリスト読み込み** — `docs/business-requirement-document-master-list.md` を読み込む
3. **質問項目の抽出・正規化** — 各ファイルの質問テーブルをパースし、質問 ID を生成する
4. **D01〜D21 マッピング** — Primary D / Contributing D を判定する（`.github/instructions/requirement-classification.instructions.md` の §2 マッピングルールに従う）
5. **状態判定** — Confirmed / Tentative / Unknown を判定する（§3 状態判定ルールに従う）
6. **カバレッジ分析** — D クラス別のカバレッジと不足項目を分析する（§5 カバレッジ分析ルールに従う）
7. **status.md 生成** — `work/business-requirement-document-status.md` を §4 テンプレートに従い生成・更新する
8. **敵対的レビュー** — AGENTS.md §7 に従い 5 軸（要件充足性/技術的正確性/整合性/非機能品質/捏造検出）で成果物をレビューし、Critical 指摘を修正する

## 実行パラメータ

| パラメータ | 値 |
|-----------|---|
| スコープ | `{aqrc_scope}` |
| force_refresh | `{aqrc_force_refresh}` |
{aqrc_target_files_section}

## 入力
- `qa/*.md`（スコープに応じてフィルタリング）
- `docs/business-requirement-document-master-list.md`
- `.github/instructions/requirement-classification.instructions.md`

## 出力
- `work/business-requirement-document-status.md`（生成・更新）

## 依存
- なし（最初に実行）

## 完了条件
- `work/business-requirement-document-status.md` が生成・更新されている
- 敵対的レビューで Critical 指摘が 0 件
- 完了時に自身に `aqrc:done` ラベルを付与すること{additional_section}
