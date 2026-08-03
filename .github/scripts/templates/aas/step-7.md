{root_ref}
## 目的
サービスカタログのAPI一覧・依存関係マトリクス・データモデルを根拠に、TDDのためのプロジェクト全体テスト戦略書を作成する。
本ステップは Web アプリのオンラインテストに加え、データフロー型アプリの**バッチテスト方針**も同一テスト戦略に統合する。APP-ID 横断の単一の真実源（SoT）として、テスト方針の重複定義を防ぐ。

## バッチテスト方針統合観点
`docs/catalog/app-catalog.md` にデータフロー型 APP-ID が含まれる場合、当該 APP-ID 向けのテスト方針も本戦略書に統合すること。per-job 個別テスト仕様は ADFD Step.3 で生成されるため、本ステップでは戦略レベルの方針に絞り重複を避ける。ADFD Step.3 は本戦略書（`docs/catalog/test-strategy.md`）を入力に参照する前提とする（T3.3 で入力切替）。
- 冪等性テスト方針（同一入力での再実行が同一結果になることを担保するテスト範囲）
- データ品質テスト方針（欠損・重複・遅延データに対する境界条件テスト）
- 大量データテスト方針（性能・スループット・メモリ／ストレージ消費の検証方針。旧パフォーマンステスト方針もここに統合する）
- 障害注入・復旧テスト方針（タイムアウト・部分失敗・リトライ・補償動作の検証方針）
- 不明な項目は推測せず `TBD` または `不明（要確認）` と明記する

データフロー型 APP-ID が存在しない場合、バッチテスト方針セクションは作成しない。ただし Web／オンラインアプリの非同期メッセージング（Queue/Event ベース）に関する冪等性・重複配送テストは、既存のテストダブル戦略および依存パターン方針の中で扱う。
該当観点の反映先は、`Arch-TDD-TestStrategy` Agent の既存セクション構造に従い、テスト分類定義の節にバッチ固有テスト種別を追加、Polyglot Persistence テスト方針の節にデータ品質・ストレージ観点を接続、網羅性チェックの節にデータフロー型 APP-ID の反映有無を追加すること（Agent 出力契約に未対応の場合は T4.5 で対応する前提とする）。

## 入力
- `docs/catalog/service-catalog-matrix.md`
- `docs/catalog/data-model.md`
- `docs/catalog/domain-analytics.md`
- `docs/catalog/service-catalog.md`
- `docs/catalog/app-catalog.md`（アプリケーション一覧）
- `docs/catalog/data-catalog.md`（存在すれば参照）

## 出力
- `docs/catalog/test-strategy.md`

{existing_artifact_policy}

## Custom Agent
`Arch-TDD-TestStrategy` を使用

## 依存
- Step.6（サービスカタログ）が `aas:done` であること

## アプリケーション粒度
📋 `docs/catalog/app-catalog.md` のアプリケーション一覧（APP-ID）を参照し、テスト戦略書にアプリ単位のサービス分類を考慮すること。

## 完了条件
- `docs/catalog/test-strategy.md` が作成されている
{completion_instruction}{additional_section}
