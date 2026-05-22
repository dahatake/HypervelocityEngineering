# アーキテクチャ要件: APP-05

> 作成日: 2026-03-16
> 参照: docs/catalog/app-catalog.md

---

## 基本情報

- **app_id**: APP-05
- **app_name**: CS・AIチャットボット

---

## system_overview

CS担当者と顧客がWebブラウザ経由でチャットを行い、AIが問い合わせを自動分類・回答し、必要に応じてCS担当者（有人エージェント）へ引き継ぐクラウドベースのWebアプリケーション。

---

## client_type

- **client_type**: web

---

## realtime

- **required**: false
- **target_latency_ms**: （任意。チャット応答は数秒程度を許容）
- **jitter_sensitive**: low
- **realtime_scope**: （N/A）

> ※ チャット応答はUXとして低遅延が望ましいが、厳密なリアルタイムSLAは不要（数秒以内の応答を想定）

---

## scalability

- **growth_expected**: medium
- **peak_variation**: medium
- **expected_users**: （TBD: CS担当者数十名 + 顧客問い合わせ量に依存）

---

## offline

- **required**: false
- **offline_scope**: （N/A）

---

## security_compliance

- **data_sensitivity**: medium
- **regulations**: 個人情報保護法（チャットログに氏名・問い合わせ内容含む）
- **cloud_allowed**: yes
- **data_residency**: jp-only

---

## cost

- **preference**: balanced
- **horizon_years**: 3

---

## priorities

1. **scalability** — level: high（問い合わせ量の増加・キャンペーン時のピークに対応）
2. **cost** — level: medium（クラウド従量課金でコスト効率を重視）
3. **security** — level: medium（個人情報を含むチャットログの保護）

---

## constraints

- CS担当者はWebブラウザで利用（専用クライアントインストール不要）
- 顧客向けインターフェースもWeb（モバイルブラウザ含む）
- 有人引継ぎ時は既存CSチケットシステム（外部SoR）と連携
- チャットログは個人情報マスキング処理が必要（APP-01と連携）
- オフライン利用は対象外（常時インターネット接続前提）
