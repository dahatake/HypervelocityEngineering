{root_ref}
## 目的
レイヤー2成果物の要約インデックスを生成する。

## 入力
- `docs-generated/components/*.md`（Step.3.x 成果物）

## 出力
- `docs-generated/component-index.md`

## Custom Agent
`Doc-ComponentIndex`

## 依存
- Step.3.1〜Step.3.5 が `adoc:done`

## 完了条件
- `docs-generated/component-index.md` が作成されている
{completion_instruction}{additional_section}
