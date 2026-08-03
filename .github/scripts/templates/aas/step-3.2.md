{root_ref}
## 目的
ユースケース文書とドメイン分析結果を根拠に、サービス一覧を抽出し、docs/catalog/service-catalog.md を作成する。
本ステップは Web アプリのオンラインサービスに加え、データフロー型アプリの**バッチサービス／ジョブ**も同一カタログに含める。APP-ID 横断の単一の真実源（SoT）として、サービスの重複定義を防ぐ。

## バッチサービス（ジョブ）を含める観点
`docs/catalog/app-catalog.md` にデータフロー型 APP-ID が含まれる場合、当該 APP-ID に紐づくジョブ／処理単位を、処理パターンやトリガー種別に依らず「サービス候補」として抽出すること（例: ETL/ELT、CDC、マイクロバッチ、集計、移行、ストリーム処理など）。
データフロー型 APP-ID が存在しない場合は既存フォーマットを維持してよい。存在する場合は、オンラインサービスを含む全サービス行に `種別: オンライン / バッチ / ストリーミング` を明記する。
- 不明な項目は推測せず `TBD` または `不明（要確認）` と明記する。

該当観点は、`Arch-Microservice-ServiceIdentify` Agent の既存サマリ表・詳細セクションに、根拠付きで反映すること（Agent 側に未対応列がある場合は新列として補う）。

## 入力
- `docs/catalog/use-case-catalog.md`
- `docs/catalog/domain-analytics.md`
- `docs/catalog/app-catalog.md`（アプリケーション一覧）

## 出力
- `docs/catalog/service-catalog.md`

{existing_artifact_policy}

## Custom Agent
`Arch-Microservice-ServiceIdentify` を使用

## 依存
- Step.3.1（ドメイン分析）が `aas:done` であること

## アプリケーション粒度
📋 `docs/catalog/app-catalog.md` のアプリケーション一覧（APP-ID）を参照し、各サービス候補に APP-ID との紐付け（N:N）を行うこと。

## 完了条件
- `docs/catalog/service-catalog.md` が作成されている
{completion_instruction}{additional_section}
