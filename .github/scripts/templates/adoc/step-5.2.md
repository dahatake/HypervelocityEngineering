{root_ref}
## 目的
依存関係マップを作成し、循環依存を分析する。

## 入力
- `docs-generated/component-index.md`

## 出力
- `docs-generated/architecture/dependency-map.md`

{existing_artifact_policy}

## Custom Agent
`Doc-DependencyMap`

## 依存
- Step.4 が `adoc:done`

## 完了条件
- `docs-generated/architecture/dependency-map.md` が作成されている
{completion_instruction}{additional_section}
