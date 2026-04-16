{root_ref}
## 目的
API 関連サマリーから API 仕様書を生成する。

## 入力
- `docs-generated/files/*.md`（Step.2.x 成果物）

## 出力
- `docs-generated/components/api-spec.md`

## Custom Agent
`Doc-APISpec`

## 依存
- Step.2.1〜Step.2.5 が `adoc:done`

## 完了条件
- `docs-generated/components/api-spec.md` が作成されている
- 完了時に自身に `adoc:done` ラベルを付与すること{additional_section}
