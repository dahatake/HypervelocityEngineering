{root_ref}
## 目的
テストコードサマリー群からテスト仕様サマリーを生成する。

## 入力
- `docs-generated/files/*.md`（テスト関連）

## 出力
- `docs-generated/components/test-spec-summary.md`

{existing_artifact_policy}

## Custom Agent
`Doc-TestSpecSummary`

## 依存
- Step.2.2 が `adoc:done`

## 完了条件
- `docs-generated/components/test-spec-summary.md` が作成されている
{completion_instruction}{additional_section}
