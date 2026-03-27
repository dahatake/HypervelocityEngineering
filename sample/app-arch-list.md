# アプリケーション アーキテクチャ推薦リスト

> 生成元: `docs/app-list.md`（APP-01〜APP-08、8件）  
> 作成日: 2026-03-16  
> 最終更新日: 2026-03-25  
> エージェント: Arch-ArchitectureCandidateAnalyzer  
> ステータス: **APP-05 ✅完了 / その他7APP ❌未処理（入力ファイルなし）**

---

## A) サマリ表（全APP横断）

| APP-ID | APP名 | 推薦アーキテクチャ | Confidence | 入力ステータス |
|--------|-------|-------------------|-----------|-------------|
| APP-01 | 会員管理・同意基盤 | — | — | ❌未処理（入力ファイルなし） |
| APP-02 | ロイヤルティ台帳・ルールエンジン | — | — | ❌未処理（入力ファイルなし） |
| APP-03 | 特典・リワード管理 | — | — | ❌未処理（入力ファイルなし） |
| APP-04 | マーケティング自動化・キャンペーン基盤 | — | — | ❌未処理（入力ファイルなし） |
| APP-05 | CS・AIチャットボット | Webフロントエンド + クラウド | 高 | ✅完了 |
| APP-06 | 顧客データ統合基盤（CDP/AI/ML） | — | — | ❌未処理（入力ファイルなし） |
| APP-07 | パートナー連携API | — | — | ❌未処理（入力ファイルなし） |
| APP-08 | 財務算定・KPI管理基盤 | — | — | ❌未処理（入力ファイルなし） |

---

## B) 各APPの詳細

### APP-05: CS・AIチャットボット

> 関連: UC-06 / CAP-05（AIチャット・顧客サポート）/ SVC-05 / MVP区分: P1  
> UC-06 KPI: 自動解決率、有人引継ぎ率、顧客満足度（CSAT）（REC-06）

#### 1) 結論（Recommended Architecture）

**Webフロントエンド + クラウド**

#### 2) Confidence

**高** — 必須入力が全て揃い、矛盾なし、仮定なし

#### 3) 入力要約

| 項目 | 値 |
|---|---|
| client_type | web |
| realtime.required | false |
| scalability.growth_expected | medium |
| scalability.peak_variation | medium |
| offline.required | false |
| security_compliance.data_sensitivity | medium |
| security_compliance.cloud_allowed | yes |
| security_compliance.data_residency | jp-only |
| cost.preference | balanced |
| priorities | scalability=high, cost=medium, security=medium |
| regulations | 個人情報保護法 |
| cost.horizon_years | 3 |
| constraints | Webブラウザ利用（モバイルブラウザ含む）、CSチケット連携、PIIマスキング必要（APP-01連携） |

- **前提**: CSおよび顧客がWebブラウザ経由で利用（モバイルブラウザ含む）。AIによる自動応答・有人引継ぎをクラウドで提供。APP-02 への残高/明細照会API連携あり（連携カタログ参照）。
- **不足/仮定**: expected_users が TBD（任意項目のため Confidence に影響なし）

#### 4) 除外（hard constraints）

| 除外候補 | 理由 |
|---|---|
| モバイルアプリ + クラウド | client_type=web のため除外 |
| モバイルアプリ + オンプレミス | client_type=web のため除外 |
| デスクトップアプリ + クラウド | client_type=web のため除外 |
| デスクトップアプリ + オンプレミス | client_type=web のため除外 |
| スタンドアロンPCアプリ | client_type=web のため除外 |
| 組み込みシステム（スタンドアロン） | client_type=web のため除外 |
| IoTデバイス + クラウド | client_type=web のため除外 |
| IoTデバイス + エッジ+クラウド | client_type=web のため除外 |
| データバッチ処理 | client_type=web（フロントエンド系）のため除外 |

**残候補**: Webフロントエンド + クラウド / Webフロントエンド + オンプレミス / ハイブリッドクラウド

> ※ data_residency=jp-only のため、クラウド利用候補（Webフロントエンド+クラウド / ハイブリッドクラウド）は日本リージョン固定・越境なしが前提条件。

#### 5) スコア上位（Top 3）

軸の重み: scalability=3（high）, cost=2（medium）, security=2（medium）, realtime=1, offline=1  
スコア換算: ◎=3, ○=2, △=1, ×=0

| 順位 | 候補 | 合計スコア | realtime(×1) | scalability(×3) | offline(×1) | security(×2) | cost(×2) |
|---|---|---|---|---|---|---|---|
| 1位 | Webフロントエンド + クラウド | **18** | △=1 | ◎=9 | ×=0 | △=2 | ◎=6 |
| 2位 | ハイブリッドクラウド | **17** | ○=2 | ○=6 | △=1 | ◎=6 | △=2 |
| 3位 | Webフロントエンド + オンプレミス | **13** | ○=2 | △=3 | ×=0 | ◎=6 | △=2 |

#### 6) 比較表（上位3つ）

| 軸 | Webフロントエンド + クラウド | ハイブリッドクラウド | Webフロントエンド + オンプレミス |
|---|---|---|---|
| realtime | △ スケーラブルだがWAN遅延あり | ○ エッジ処理可能 | ○ 低遅延 |
| scalability | ◎ オートスケール得意 | ○ 中程度 | △ 増設に工数 |
| offline | × ブラウザ必須 | △ 限定的 | × ブラウザ必須 |
| security | △ クラウドセキュリティ | ◎ 独自制御可能 | ◎ 完全内部制御 |
| cost | ◎ 従量課金・管理コスト低 | △ ハイブリッド運用コスト増 | △ インフラ初期投資大 |

#### 7) トレードオフ

- **優先**: スケーラビリティ（キャンペーン時のピーク対応）とコスト効率（従量課金）を優先。cloud_allowed=yes かつ data_residency=jp-only のため日本リージョン固定で対応。
- **割り切り**: セキュリティは「medium」でありクラウドの標準機能（暗号化・アクセス制御）で対応。完全内部制御が必要な high の場合はオンプレミスが有力だが、本APPでは必要なし。
- **割り切り**: realtime は△（厳密な低遅延SLAなし）。チャット応答の数秒遅延は許容。
- **補足**: 2位 ハイブリッドクラウドとのスコア差は1ポイント（18 vs 17）。セキュリティ要件が high に引き上げられた場合、ハイブリッドクラウドが有力候補に浮上する。

#### 8) 次のアクション

1. **日本リージョン固定 + DR/BCP設計**: data_residency=jp-only のため、利用クラウドサービスの日本リージョン固定・越境なしを設計書で明示する。リージョン障害時のDR/BCP計画（RPO/RTO目標）を策定する（`app-list.md` §7「可用性・DR」参照）
2. **セキュリティ統合設計（暗号化・鍵管理・PII・権限・責任分界）**: regulations=個人情報保護法に基づき、保存時暗号化（AES-256等）・通信暗号化（TLS 1.2+）・鍵管理方式・PIIマスキング/仮名化（APP-01連携）・CS担当者/顧客の権限設計（RBAC、`app-list.md` §7参照）・責任分界を統合設計する。※ APP-01 が未処理のため連携仕様は暫定。APP-01 判定完了後に再確認要
3. **オートスケール + 性能目標設計**: scalability=high 対応。Kubernetes HPA / Azure App Service スケーリング等によるスケールアウト設計。SLI/SLO定義（`app-list.md` §7 暫定3段階SLA参照）、チャット応答SLA目標設定、キャンペーンピーク時の負荷テスト計画を策定する。UC-06 KPI（自動解決率・有人引継ぎ率・CSAT）のモニタリング基盤も設計する
4. **AIモデル運用設計 + ガバナンス**: 自動応答 vs 有人引継ぎ判断のスコア閾値を設計・検証する（TBD）。AI利用ガバナンス（`app-list.md` §7参照）に基づき、AI出力の監査ログ・NGワードフィルタ・バイアス/ドリフト監視を設計する。AI障害時はルールベースにフォールバック。ナレッジDB更新フロー・責任者をCS部門と合意する（TBD）
5. **CSチケット + APP-02 連携I/F設計**: 有人引継ぎ時のCSチケット連携（APIコール・データフォーマット・障害時フォールバック）を確定する。APP-02への残高/明細照会API連携（連携カタログ: 同期API、失敗時は一般回答にフォールバック）の詳細設計を行う。冪等設計必須（`app-list.md` §7「連携失敗時処理」参照）
6. **チャットログ保全 + 監査設計**: 保持期間（`app-list.md` §7 暫定: 操作3年）・アクセス制御・監査証跡を個情法要件に基づき設計する（法務確認要）。監査ログ基盤の方針は DEC-006（共通 vs 分散: TBD）に従う。インシデント対応（検知→通知→対応の時間枠）も定義する
7. **レスポンシブUI + 可観測性設計**: constraints「モバイルブラウザ含む」に対応するレスポンシブUI設計（WCAG準拠推奨）。APM・ログ集約・アラート・分散トレーシング設計（`app-list.md` §7「可観測性」参照）を策定する

---

## C) 未処理・不足APP一覧

| APP-ID | APP名 | ステータス | 理由 | 必要なアクション |
|--------|-------|----------|------|---------------|
| APP-01 | 会員管理・同意基盤 | ❌未処理（入力ファイルなし） | `docs/architecturally-requirements-app-01.md` が存在しないため、アーキテクチャ選定を実施できませんでした | `docs/architecturally-requirements-app-01.md` を作成し、再度本エージェントを実行してください |
| APP-02 | ロイヤルティ台帳・ルールエンジン | ❌未処理（入力ファイルなし） | `docs/architecturally-requirements-app-02.md` が存在しないため、アーキテクチャ選定を実施できませんでした | `docs/architecturally-requirements-app-02.md` を作成し、再度本エージェントを実行してください |
| APP-03 | 特典・リワード管理 | ❌未処理（入力ファイルなし） | `docs/architecturally-requirements-app-03.md` が存在しないため、アーキテクチャ選定を実施できませんでした | `docs/architecturally-requirements-app-03.md` を作成し、再度本エージェントを実行してください |
| APP-04 | マーケティング自動化・キャンペーン基盤 | ❌未処理（入力ファイルなし） | `docs/architecturally-requirements-app-04.md` が存在しないため、アーキテクチャ選定を実施できませんでした | `docs/architecturally-requirements-app-04.md` を作成し、再度本エージェントを実行してください |
| APP-06 | 顧客データ統合基盤（CDP/AI/ML） | ❌未処理（入力ファイルなし） | `docs/architecturally-requirements-app-06.md` が存在しないため、アーキテクチャ選定を実施できませんでした | `docs/architecturally-requirements-app-06.md` を作成し、再度本エージェントを実行してください |
| APP-07 | パートナー連携API | ❌未処理（入力ファイルなし） | `docs/architecturally-requirements-app-07.md` が存在しないため、アーキテクチャ選定を実施できませんでした | `docs/architecturally-requirements-app-07.md` を作成し、再度本エージェントを実行してください |
| APP-08 | 財務算定・KPI管理基盤 | ❌未処理（入力ファイルなし） | `docs/architecturally-requirements-app-08.md` が存在しないため、アーキテクチャ選定を実施できませんでした | `docs/architecturally-requirements-app-08.md` を作成し、再度本エージェントを実行してください |

### 入力ファイル作成方法

各APPの入力ファイル（`docs/architecturally-requirements-app-xx.md`）は、以下の最小入力項目を含めて作成してください（詳細は `users-guide/02-App-Selection.md` Step 2 を参照）：

```
- app_id: APP-xx
- app_name: （アプリケーション名）
- system_overview: （1〜3文の概要：誰が/何を/どこで使う）
- client_type: web|mobile|desktop|embedded|iot|batch|mixed
- realtime:
  - required: true|false
- scalability:
  - growth_expected: low|medium|high
  - peak_variation: low|medium|high
- offline:
  - required: true|false
- security_compliance:
  - data_sensitivity: low|medium|high
  - cloud_allowed: yes|no|partial
- cost:
  - preference: low-initial|balanced|low-tco
- priorities:
  - - axis: realtime|scalability|offline|security|cost
      level: must|high|medium|low
```

---

## D) 横断分析

判定完了APP（1件）のみのため、APP間の横断分析は省略。APP-01〜APP-04、APP-06〜APP-08 の判定完了後に横断分析を更新する。

> ※ 判定完了APPが2件以上になった時点で横断分析（パターン分布・共通基盤化可能性・アーキテクチャ整合性リスク）を追記します。

---

## E) 処理統計

```
処理統計:
- 全APP数: 8
- 判定完了: 1（✅完了: 1、⚠️仮定付き: 0）
- 判定未完了: 7（⚠️判定中断: 0、❌入力ファイルなし: 7）
- 横断分析: 未実施（判定完了APP数不足）
```
