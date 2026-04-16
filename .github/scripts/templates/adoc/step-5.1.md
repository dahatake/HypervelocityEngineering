{root_ref}
## 目的
コンポーネントインデックスからアーキテクチャ概要を生成する。

## 入力
- `docs-generated/component-index.md`

## 出力
- `docs-generated/architecture/overview.md`

## Custom Agent
`Doc-ArchOverview`

## 依存
- Step.4 が `adoc:done`

## 完了条件
- `docs-generated/architecture/overview.md` が作成されている
- 完了時に自身に `adoc:done` ラベルを付与すること{additional_section}
