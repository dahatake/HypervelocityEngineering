{root_ref}
## 目的
テストコードサマリー群からテスト仕様サマリーを生成する。

## 入力
- `docs-generated/files/*.md`（テスト関連）

## 出力
- `docs-generated/components/test-spec-summary.md`

## Custom Agent
`Doc-TestSpecSummary`

## 依存
- Step.2.2 が `adoc:done`

## 完了条件
- `docs-generated/components/test-spec-summary.md` が作成されている
- 完了時に自身に `adoc:done` ラベルを付与すること{additional_section}
