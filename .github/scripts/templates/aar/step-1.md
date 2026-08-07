{root_ref}

{app_arch_scope_section}
## 目的
既に稼働している API / データ資産を持つサービスに対し、**Agentic Retrieval 部分だけ**を後付けするための製品非依存な機能要件詳細を作成する。

## 入力
- `docs/catalog/app-catalog.md`（アプリケーション一覧 — 対象 APP-ID のスコープ判定根拠。存在しない場合はスコープ絞り込みなしで全件処理）
- `docs/catalog/service-catalog.md`
- `docs/catalog/domain-analytics.md`
- `docs/services/{serviceId}-{serviceNameSlug}-description.md`

## 出力
- `docs/services/{serviceId}-agentic-retrieval-spec.md`

## 本ワークフロー固有の前提
- 対象サービスの API / データストアは **既に存在する**前提で進める。作り直しを提案しない。
- 既存資産のどれを Knowledge Source 候補とするかを、根拠付きで列挙する。
- 対象サービスが 0 件の場合は `{WORK}work-status.md` に「対象なし」と記録し、成果物なしで完了する。

{existing_artifact_policy}

## Custom Agent
`Arch-AgenticRetrieval-Detail` を使用

## 完了条件
- 対象サービスごとに `docs/services/{serviceId}-agentic-retrieval-spec.md` が作成されている
- Knowledge Source 候補が既存資産と対応づけられている
{completion_instruction}{app_id_section}{additional_section}
