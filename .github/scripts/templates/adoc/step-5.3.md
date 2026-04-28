{root_ref}
## 目的
インフラ依存・ベンダーロックインを分析する。

## 入力
- `docs-generated/component-index.md`
- `docs-generated/files/*.md`（設定・IaC 関連）

## 出力
- `docs-generated/architecture/infra-deps.md`

## Custom Agent
`Doc-InfraDeps`

## 依存
- Step.4 が `adoc:done`

## 完了条件
- `docs-generated/architecture/infra-deps.md` が作成されている
{completion_instruction}{additional_section}
