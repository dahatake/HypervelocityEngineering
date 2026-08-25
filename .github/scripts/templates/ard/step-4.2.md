{root_ref}
## 目的
アプリケーションカタログに列挙された全APPについて、canonicalなAPP別要求定義書を順次upsertする。

## 入力
- `docs/catalog/app-catalog.md`
- `docs/catalog/use-case-catalog.md`
- `docs/architectural-requirements-app-NNN.md`（既存文書は保持してupsert）
- 明示添付資料・回答済みQA・staleness合格済みknowledge（存在する場合のみ）

## 出力
- `docs/architectural-requirements-app-NNN.md`（app-catalogの全APP）

{existing_artifact_policy}

## Custom Agent
`Arch-ApplicationRequirementDefinition`

## 依存
- Step 4.1（アプリケーションリスト作成）

## 実行制約
- 単一エージェントでAPPを出現順に処理し、fan-outしない
- 既存confirmed内容、source-backed ID、人手追記、orphan文書を削除しない
- 全APPのcoverageとschemaをfail-closedで検証する

## 完了条件
- app-catalogの全APPに対応するcanonical fileが存在する
- 各文書が固定schemaを満たす
- orphan文書は削除せず警告として記録されている
{completion_instruction}{additional_section}
