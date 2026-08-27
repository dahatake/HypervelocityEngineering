# ADA Fan-out per-element 追加指示

このサブタスクは ADA（Agent Data Architecture）の fan-out 子であり、サービス `{{key}}` のみを対象とする。

## 対象
- サービス詳細仕様: `docs/services/{{key}}-*-description.md`

## 必須参照
- `docs/catalog/service-catalog.md`
- `docs/catalog/data-catalog.md`
- `docs/catalog/domain-analytics.md`

## ADA 固有の制約
- **画面カタログは存在しない**。`docs/catalog/screen-catalog-APP-*.md` を入力として要求しない。API の導出根拠はユースケース・ドメイン分析・データカタログとする。
- `docs/catalog/service-catalog-matrix.md` も存在しない。参照しない。

## 並列実行ルール
- 自身の対象 `{{key}}` 以外には書き込まない。
- 共通カタログへの追記は行わない（並列子間で競合するため）。

## オーバーエンジニアリング禁止（共通ルール）
- **オーバーエンジニアリングは絶対に禁止**です。
- 指示・要件にない汎用化・抽象化・将来予測による拡張点の先回り追加を行わない。
- 要件に根拠のない API・イベント・権限を創作しない。根拠が無い項目は `TBD（要確認）` とする。
