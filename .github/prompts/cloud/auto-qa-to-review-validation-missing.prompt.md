{{VALIDATION_MISSING_MARKER}}

## ⚠️ 検証実施記録が確認できません（auto-approve-ready 付与保留）

@copilot PR body に `## 検証結果` セクションと `<!-- validation-confirmed -->` マーカーを追記してください。

PR body またはコメントに検証実施記録（`validation-confirmed` マーカー / `Validation`・`検証` 見出し / `検証:` 形式）が見つからないため、`auto-approve-ready` ラベルの付与を保留しました。

**.github/copilot-instructions.md §0 要件**: 最低1つの検証を実施すること（テスト/ビルド/静的解析のいずれかを行い、できない場合は理由と代替を明記すること）。

### 対処方法

以下いずれかを PR body またはコメントに追記してください（推奨順）:

1. HTML コメントマーカー（推奨）
   - `<!-- validation-confirmed -->`
2. 見出し方式
   - `## 検証`
   - `## 検証結果`
   - `## Validation`
3. 箇条書き / 強調方式
   - `- 検証: pytest 実行済`
   - `**検証**: ビルド成功`
   - `> Validation: lint OK`

> ℹ️ このコメントは `auto-qa-to-review-transition.yml` によって自動投稿されました。
