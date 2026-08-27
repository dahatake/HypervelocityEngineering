{root_ref}
## 目的
ファイルサマリー群から技術的負債を集約し、優先度を整理する。

## 入力
- `docs-generated/files/*.md`（Step.2.x 成果物）

## 出力
- `docs-generated/components/tech-debt.md`

{existing_artifact_policy}

## Custom Agent
`Doc-TechDebt`

## 依存
- Step.2.1〜Step.2.5 が `adoc:done`

## 完了条件
- `docs-generated/components/tech-debt.md` が作成されている
{completion_instruction}{additional_section}
