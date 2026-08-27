{root_ref}
## 目的
ADI Step 1.1 として、D01〜D21 の各業務分類ごとに正規化済み原本から質問票を生成する。

## モード
`original-docs-questionnaire`

## Custom Agent
`QA-DocConsistency`

## 実行パラメータ

| パラメータ | 値 |
|-----------|---|
| target_scope | `{adi_target_scope}` |
| depth | `{adi_depth}` |
| focus_areas | `{adi_focus_areas}` |

## 入力
- `docs/original-design-doc-ingest/index.json`
- `docs/original-design-doc-ingest/*/content.md`
- `template/business-requirement-document-master-list.md`
- （任意）`knowledge/{{key}}-*.md`

## 出力
- `qa/{key}-original-docs-questionnaire.md`（fan-out 子毎に 1 ファイル。`{key}` は `D01`〜`D21`）

{existing_artifact_policy}

## 完了条件
- `qa/{key}-original-docs-questionnaire.md` が生成されている
- 出力フォーマットが Agent 仕様 `## 6) Originalドキュメント整合性チェック` に準拠している
- `index.json` と正規化済み `content.md` のみを根拠にしている
- `docs-original/` を直接走査していない
- 質問が 0 件の場合もサマリーに `総質問数: 0` と `質問なし` が明記されている{additional_section}