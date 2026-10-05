{root_ref}
## 目的
ユースケース文書を根拠に、実装手段を仕分けし、アプリケーションリストを作成する。

## 入力
- `docs/catalog/use-case-catalog.md`
- `docs/recommended-kpi-okr.md`（任意）

## 出力
- `docs/catalog/app-catalog.md`

{existing_artifact_policy}

## Custom Agent
`Arch-ApplicationAnalytics`

## 依存
- Step 3.3（ユースケースカタログ統合）

## ID 台帳
- カタログを書き終えたら `python .github/scripts/check-id-ledger.py --bootstrap --warn-only` を実行し、`docs/catalog/id-ledger.md` をカタログから作り直す（FR-IDL-01）。台帳を手で編集しない。並列に動く他の Step と同じ結果になるよう、台帳はカタログから決定的に生成するためである。表示された違反は作業ログに記録する。

## 完了条件
- `docs/catalog/app-catalog.md` が作成されている
{completion_instruction}{additional_section}
