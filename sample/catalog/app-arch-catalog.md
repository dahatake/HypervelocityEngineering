# アプリケーション アーキテクチャ カタログ（app-arch-catalog.md）

> **作成根拠**: `docs/app-catalog.md`（APP-01〜APP-09）および `docs/architectural-requirements-app-xx.md`（存在するもの）  
> **作成日**: 2026-04-08  
> **作成エージェント**: Arch-ArchitectureCandidateAnalyzer  
> **ステータス**: Draft（全APPデフォルト適用 — 入力ファイル未作成）

---

## A) サマリ表（全APP横断）

| APP-ID | APP名 | 推薦アーキテクチャ | Confidence | 入力ステータス |
|--------|-------|-------------------|-----------|-------------|
| APP-01 | 会員ポータル | Webフロントエンド + クラウド | — | ⚠️デフォルト適用（入力ファイルなし） |
| APP-02 | ロイヤルティ台帳・ルールエンジン | Webフロントエンド + クラウド | — | ⚠️デフォルト適用（入力ファイルなし） |
| APP-03 | 特典カタログ・交換管理 | Webフロントエンド + クラウド | — | ⚠️デフォルト適用（入力ファイルなし） |
| APP-04 | CDP・データ統合基盤 | Webフロントエンド + クラウド | — | ⚠️デフォルト適用（入力ファイルなし） |
| APP-05 | AI・キャンペーン配信 | Webフロントエンド + クラウド | — | ⚠️デフォルト適用（入力ファイルなし） |
| APP-06 | AI CSサポート | Webフロントエンド + クラウド | — | ⚠️デフォルト適用（入力ファイルなし） |
| APP-07 | パートナー連携基盤 | Webフロントエンド + クラウド | — | ⚠️デフォルト適用（入力ファイルなし） |
| APP-08 | 財務・分析・KPI | Webフロントエンド + クラウド | — | ⚠️デフォルト適用（入力ファイルなし） |
| APP-09 | 権限・監査・同意ガバナンス | Webフロントエンド + クラウド | — | ⚠️デフォルト適用（入力ファイルなし） |

> **注記**: 全APPにデフォルト推薦「Webフロントエンド + クラウド」を適用しました。より正確な推薦を得るには、各APPの `docs/architectural-requirements-app-xx.md` を作成し、本エージェントを再実行してください。

---

## B) 各APPの詳細

デフォルト適用のAPPは詳細セクションを省略します（要件ベース判定なし）。

各APPの特性（`docs/app-catalog.md` より参考）と、入力ファイル作成時の推奨 `client_type` を以下に示します。

| APP-ID | APP名 | 主責務（要旨） | 推奨 client_type 候補 | 優先考慮NFR |
|--------|-------|--------------|----------------------|-----------|
| APP-01 | 会員ポータル | 顧客セルフサービスUX（登録・同意・残高照会・特典選択） | web または mixed（Web + モバイル） | 登録UX ≤3タップ / WCAG AA / OAuth2 |
| APP-02 | ロイヤルティ台帳・ルールエンジン | ポイント付与・消込・ランク管理・ルール設定 | web（管理者UI） | 台帳整合性（冪等・二重計上防止）/ 付与SLA ≤30秒 |
| APP-03 | 特典カタログ・交換管理 | 特典カタログ登録/公開・在庫管理・交換処理・コード発行 | web または mixed | 交換処理べき等性 / コード発行遅延 ≤2秒 |
| APP-04 | CDP・データ統合基盤 | 顧客データ収集/変換/名寄せ/品質管理・AI/MLプラットフォーム | batch（データパイプライン） | データ品質 ≥95%ID一致率 / GDPR対応PII分離 |
| APP-05 | AI・キャンペーン配信 | AI推奨・オムニチャネルキャンペーン設計/配信最適化・生成AI | mixed（Web管理UI + batch配信） | 配信遅延 ≤5分（バッチ）/ AI説明可能性 |
| APP-06 | AI CSサポート | AIチャット問い合わせ対応・有人引継ぎ（GPT-5.4） | web または mixed | 応答 ≤3秒 / 個人情報マスキング |
| APP-07 | パートナー連携基盤 | パートナーポイント交換設定・交換実行・清算レポート生成 | web（管理UI） | 交換べき等性 / 補償トランザクション / 清算精度100% |
| APP-08 | 財務・分析・KPI | breakage見積・ポイント負債算定・ERP仕訳連携・KPIダッシュボード | batch または mixed（batch + Web UI） | 決算締め対応スケジュール / 監査証跡100% |
| APP-09 | 権限・監査・同意ガバナンス | ロール/権限管理・同意記録/撤回反映・監査ログ収集 | web（管理者） | ログ改ざん不可 / 同意反映 ≤即時 / GDPR準拠 |

> **💡 ヒント**: APP-04（CDP・データ統合）および APP-08（財務・分析・KPI）は `client_type: batch` が適切な可能性があります。
> `docs/architectural-requirements-app-04.md` / `docs/architectural-requirements-app-08.md` を作成して再実行すると、
> 「データバッチ処理」が推薦される可能性があります。

---

## C) 未処理・不足APP一覧

該当なし

> デフォルト適用（`⚠️デフォルト適用（入力ファイルなし）`）は「処理済み」扱いであり、未処理一覧には含まれません。
> 矛盾検出による判定停止や追加質問待ちのAPPはありません。

---

## D) 横断分析

省略（判定完了APP数が0件のため）

> 全APPの `docs/architectural-requirements-app-xx.md` を作成し本エージェントを再実行すると、横断分析（パターン分布・共通基盤化可能性・APP間連携リスク）が出力されます。

---

## E) 処理統計

```
処理統計:
- 全APP数: 9
- 判定完了: 0（✅完了: 0、⚠️仮定付き: 0）
- デフォルト適用: 9（⚠️デフォルト適用（入力ファイルなし）: 9）
- 判定未完了: 0（⚠️判定中断: 0）
- 横断分析: 未実施（判定完了APP数不足）
```

---

## 入力ファイル作成ガイド

各APPの `docs/architectural-requirements-app-xx.md` を作成することで、要件に基づく正確なアーキテクチャ推薦が得られます。
詳細は `users-guide/02-app-architecture-design.md` の Step 2 を参照してください。

### 最小入力フォーマット

```markdown
- app_id: APP-xx
- app_name: アプリケーション名
- system_overview: 1〜3文の概要（誰が/何を/どこで使う）
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
  - （2〜3件推奨）
```

ファイルを作成後、本エージェントを再実行してください。入力ファイルを作成したAPPは要件ベースで判定し、未作成のAPPにはデフォルト推薦（Webフロントエンド + クラウド）が引き続き適用されます。
