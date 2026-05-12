{root_ref}
## 目的
`original-docs/` 配下の全 Markdown を横断分析し、ソフトウェア設計・開発・運用上の不明瞭点・矛盾点・ベストプラクティス逸脱を質問票として生成する。

## モード
`original-docs-questionnaire`

## Custom Agent
`QA-DocConsistency`

## 実行パラメータ

| パラメータ | 値 |
|-----------|---|
| target_scope | `{aqod_target_scope}` |
| depth | `{aqod_depth}` |
| focus_areas | `{aqod_focus_areas}` |

## 入力
- `original-docs/` 配下の Markdown
- （任意）`knowledge/D07-用語集-ドメインモデル定義書.md`

## 出力
- `qa/{key}-original-docs-questionnaire.md`（fan-out 子毎に 1 ファイル。`{key}` は `D01`〜`D21`）

## 完了条件
- `qa/{key}-original-docs-questionnaire.md` が生成されている
- 出力フォーマットが Agent 仕様 `## 6) Originalドキュメント整合性チェック` に準拠している{additional_section}
