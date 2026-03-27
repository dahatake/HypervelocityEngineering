{root_ref}
## 目的
サービスカタログおよびIoT各種成果物に基づき、マイクロサービス定義書を作成する。

## 入力
- テンプレート + 各種成果物（docs/service-catalog.md 等）

## 出力
- `docs/services/{{serviceId}}-{{serviceNameSlug}}-description.md`（サービスごとに1ファイル）

## Custom Agent
`Arch-Microservice-ServiceDetail` を使用

## 依存
- {dep}

## 完了条件
- マイクロサービス定義書がサービスカタログに基づいて全て作成されている
- 完了時に自身に `aid:done` ラベルを付与すること{additional_section}
