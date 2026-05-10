{root_ref}

{app_arch_scope_section}
## 目的
サービスカタログおよび各種成果物に基づき、マイクロサービス定義書を作成する。

## 入力
- テンプレート + 各種成果物（docs/catalog/service-catalog-matrix.md 等）
- `docs/catalog/app-catalog.md`（アプリケーション一覧）

## 出力
- `docs/services/{{serviceId}}-{{serviceNameSlug}}-description.md`（サービスごとに1ファイル）

## Custom Agent
`Arch-Microservice-ServiceDetail` を使用

## 依存
- {dep}

## アプリケーション粒度
📋 各マイクロサービス定義書の「§1 サービスメタ情報」に「利用アプリケーション」（N:N）を記載すること。`docs/catalog/app-catalog.md` の「アプリ一覧（アーキタイプ）概要」を参照。

## 完了条件
- マイクロサービス定義書がサービスカタログに基づいて全て作成されている
{completion_instruction}{remote_mcp_server_design_section}{additional_section}
