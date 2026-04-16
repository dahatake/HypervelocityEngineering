{root_ref}
## 目的
依存関係マップを作成し、循環依存を分析する。

## 入力
- `docs-generated/component-index.md`

## 出力
- `docs-generated/architecture/dependency-map.md`

## Custom Agent
`Doc-DependencyMap`

## 依存
- Step.4 が `adoc:done`

## 完了条件
- `docs-generated/architecture/dependency-map.md` が作成されている
- 完了時に自身に `adoc:done` ラベルを付与すること{additional_section}
