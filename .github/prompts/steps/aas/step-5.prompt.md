{root_ref}
## 目的
サービス一覧、データモデル、画面一覧、ドメイン分析を統合してサービスカタログを作成する。
本ステップは Web アプリのオンライン API に加え、データフロー型アプリの**ジョブ DAG・スケジュール・リトライ戦略**も同一マトリクスに統合する。APP-ID 横断の単一の真実源（SoT）として、サービス間連携の重複定義を防ぐ。

## バッチ／ジョブ統合観点
`docs/catalog/app-catalog.md` にデータフロー型 APP-ID が含まれる場合、当該 APP-ID に紐づくジョブの**サービス間連携のみ**を本マトリクスに統合すること。per-job 詳細仕様（パイプライン構造・データ変換ロジック・運用設計）は ADFD Step.1 で生成されるため、本ステップでは責務を絞り重複を避ける。
- 条件付きで Table D（ジョブ実行制御マトリクス）を追加する。列構成: `APP-ID / Job-ID / ジョブ名 / 上流Job / 下流Job / 起動条件（スケジュールまたはトリガの種別） / リトライ概要 / 冪等性・再実行安全性 / 詳細仕様リンク / 出典`
- リトライ詳細（最大試行回数・バックオフ・タイムアウト）や DLQ・補償手順は本マトリクスでは概要に留め、詳細は ADFD Step.1 の per-job 詳細仕様（`docs/dataflow/apps/...`）へリンクで委譲する
- ジョブ情報の根拠は `docs/catalog/service-catalog.md`（T1.2 でバッチサービスを含めるよう修正済み）と `docs/catalog/use-case-catalog.md` から得る
- 不明な項目は推測せず `TBD` または `不明（要確認）` と明記する

データフロー型 APP-ID が存在しない場合、Table D およびジョブ実行制御セクションは作成しない。
該当観点は、`Arch-Microservice-ServiceCatalog` Agent の出力契約に Table D 列が無い場合、T4.4 で追加する前提とする（既存 Table A/B/C は変更しない）。

## 入力
- `docs/catalog/service-catalog.md`
- `docs/catalog/data-model.md`
- `docs/catalog/screen-catalog-APP-*.md`（全 APP の per-APP 分割された画面カタログ。`Arch-UI-List` Step 1 の per-APP fan-out 出力。全 APP 分を集約読みする）
- `docs/catalog/domain-analytics.md`
- `docs/catalog/app-catalog.md`（アプリケーション一覧）

## 出力
- `docs/catalog/service-catalog-matrix.md`

{existing_artifact_policy}

## Custom Agent
`Arch-Microservice-ServiceCatalog` を使用

## 依存
- Step.4（データカタログ作成）が `aas:done` であること

## アプリケーション粒度
📋 `docs/catalog/app-catalog.md` のアプリケーション一覧（APP-ID）を参照し、Table A（画面→API）に「所属APP」（1:1）、Table C（サービス責務）に「利用APP」（N:N）を記載すること。

## 完了条件
- `docs/catalog/service-catalog-matrix.md` が作成されている
{completion_instruction}{additional_section}
