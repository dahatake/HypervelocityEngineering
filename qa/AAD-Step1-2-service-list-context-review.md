# コンテキスト確認（質問）— AAD Step.1.2 Service List

**状態**: 回答待ち
**推論許可**: なし
**対象PR**: AAD Step.1.2 サービス一覧抽出
**作成日**: 2026-03-30

---

## 質問項目

| No. | 質問 | 選択肢 | デフォルトの回答案 | 選択理由 |
|-----|------|--------|-------------------|----------|
| 1 | SVC-02（ポイント台帳）とSVC-03（付与ルールエンジン）を別サービスとして分割する方針は正しいか（同一APP-02内） | A) 別サービス維持（現行）/ B) 1サービスに統合 | A) 別サービス維持 | domain-analytics.md §BC-02「台帳整合性（ACID）とルールエンジン（高頻度変更）は変更原因・デプロイ粒度が異なる」に基づく明示的設計判断 |
| 2 | SVC-08（キャンペーン管理）とSVC-09（コンテンツ生成・承認）を別サービスとして維持すべきか | A) 別サービス維持（DEC-012根拠）/ B) 1サービスに統合 | A) 別サービス維持 | DEC-012「GeneratedContentAggregateをCampaignAggregateから分離。独立した承認ライフサイクルを持つため」の明示的決定を尊重 |
| 3 | SVC-11（パートナー設定）とSVC-12（パートナー交換・清算）を別サービスとして維持すべきか | A) 別サービス維持（DEC-011根拠）/ B) 1サービスに統合 | A) 別サービス維持 | DEC-011「PartnerConfigAggregateとPartnerExchangeTransactionAggregateを分離。変更頻度・ライフサイクルが異なる」の明示的決定を尊重 |
| 4 | SVC-15（アクセス制御）とSVC-16（監査ログ）を別サービスとして維持すべきか | A) 別サービス維持（DEC-013根拠）/ B) 1サービスに統合 | A) 別サービス維持 | DEC-013「AccessControlAggregateとAuditLogAggregateを分離。変更特性・SLAが異なる」の明示的決定を尊重 |
| 5 | SVC-05の名称として適切なものはどれか | A) 顧客エンゲージメントポータルBFF（現行）/ B) 顧客ポータルサービス / C) 会員ポータルAPI | A) 顧客エンゲージメントポータルBFF | BC-04「顧客エンゲージメントポータル」の名称と一致し、BFFパターン（Backend For Frontend）であることを明示できる |
| 6 | MVPに含めるサービスの範囲はどれか（app-list.mdのMVP={APP-01〜05, APP-10, APP-12}との対応） | A) P0対応9件（SVC-01〜06, SVC-13, SVC-15, SVC-16）/ B) コアドメイン優先5件（SVC-01/02/03/04/16）/ C) 最小3件（SVC-02/03/16）/ D) 全16件同時 | A) P0対応9件 | app-list.md MVP定義（APP-01〜05, APP-10, APP-12）に対応するサービスを全てMVPに含めることでP0 UCを全てカバーできる |
| 7 | 候補ステータス（現行: 全件「候補」）を「確定」に昇格させるタイミングはいつか | A) ブロッカー解消後に全件確定 / B) SoRが明確な候補は即「確定」（例: SVC-02/03/04）/ C) PR承認時点で全件確定 | B) SoRが明確なものを即「確定」 | SoR/BC/UC根拠が確認できるサービスを先行確定することで、後続の詳細設計を早期に開始できる |
| 8 | 次フェーズ（詳細設計書 SVC-NN-description.md）の着手優先順位はどれか | A) コアドメイン優先（SVC-02/03 → SVC-04 → SVC-01 の順）/ B) ユースケースフロー順（SVC-01 → SVC-02 → SVC-04 → SVC-05）/ C) MVP全件同時並行 | A) コアドメイン優先 | SVC-02/03（ポイント台帳・ルールエンジン）のI/Fが他サービス（SVC-04/05/12/13）の依存先となっており、先行設計で波及リスクを最小化できる |
| 9 | サービス間の非同期イベント配信基盤として何を使用するか | A) Azure Service Bus（信頼性重視、At-least-once保証）/ B) Azure Event Hubs（高スループット、ストリーム処理）/ C) Azure Event Grid（サーバーレスイベント）/ D) 混在（用途別に選択）/ E) TBD（インフラ設計フェーズで決定） | D) 混在（用途別） | 台帳イベント（PointsAwarded等）は確実配信→Service Bus、CDP/AI向けストリームはEvent Hubs、という使い分けが設計根拠に合致。最終選定はインフラ設計フェーズで確定 |
| 10 | 内部サービス間の同期通信プロトコルはどれか | A) REST/HTTP（現行設計）/ B) gRPC（高性能内部通信）/ C) REST（外部向け）+ gRPC（内部向け）混在 | A) REST/HTTP | Azure Functionsとの整合性、チーム習熟度、運用シンプルさを優先。gRPCへの移行は性能ボトルネック判明後に検討 |
| 11 | SVC-05（顧客ポータルBFF）のAPI設計スタイルはどれか | A) REST API（現行設計）/ B) GraphQL / C) REST + GraphQL混在（画面複雑度に応じて） | A) REST API | 当初のシンプルさを優先。フロントエンドの要求が複雑化した場合はGraphQL検討 |
| 12 | SVC-07（AI推論）のキャッシュTTL設計方針はどれか（DEC-010参照） | A) 推薦結果: 1時間、チャーンスコア: 24時間（仮定値）/ B) TBD（ブロッカー#7 SLA確定後）/ C) リアルタイム推論のみ（キャッシュなし） | B) TBD（ブロッカー#7 SLA確定後） | domain-analytics.md §TBD-12「キャッシュTTLはTBD（DEC-010）」とブロッカー#7（リアルタイムSLA）が解消されるまで仮定値を設定しない方が安全 |
| 13 | イベントスキーマの管理方式はどれか（例: ConsentChanged, PointsAwardedのスキーマ定義） | A) Azure Schema Registry（Event Hubs連携）/ B) Confluent Schema Registry（Kafka互換）/ C) JSONスキーマをGitリポジトリで管理 / D) TBD（イベント基盤選定後） | D) TBD（イベント基盤選定後） | Q9のイベント基盤選定に依存するため、先行決定は非合理 |
| 14 | コアドメイン（SVC-02/03）のホスティング方式はどれか | A) Azure Container Apps / B) AKS（Azure Kubernetes Service）/ C) Azure Functions Premium Plan | A) Azure Container Apps | 台帳の高可用性（99.95%）・常時稼働要件。Azure FunctionsのCold start問題を回避でき、AKSより運用コストが低い |
| 15 | SVC-07（AI/ML推論・モデル管理）のホスティング方式はどれか | A) Azure Machine Learning（マネージドAI基盤）/ B) Azure Container Apps + カスタムモデルサーバー / C) Azure Functions（軽量推論のみ） | A) Azure Machine Learning | モデル学習/評価/デプロイ/監視（MLflow対応）の統合管理が必要。app-list.md §APP-06のMLモデル管理要件に適合 |
| 16 | SVC-05（顧客ポータルBFF）の推奨デプロイ先はどれか | A) Azure Static Web Apps（フロントエンドと同梱）/ B) Azure Container Apps / C) Azure Functions（HTTP trigger）/ D) Azure API Management（集約ゲートウェイとして） | B) Azure Container Apps | コンシューマ向け高可用性（99.95%）・低レイテンシ（P95 < 2s）要件を満たすコンテナが適切。静的フロントエンドとは分離 |
| 17 | サービスメッシュ（Istio / Linkerd / Azure Service Mesh）の採用可否はどれか | A) 採用（全サービスにサイドカー注入）/ B) 不採用（アプリケーション層で対応）/ C) TBD（ホスティング方式確定後）/ D) AKS選定時のみ検討 | C) TBD（ホスティング方式確定後） | ホスティング方式（Q14/Q15/Q16）が確定する前に決定するのは時期尚早 |
| 18 | サービス間のデータ分離原則はどれか | A) 各サービス専用DB（物理DB分離）/ B) スキーマ分離（同一DBサーバー、スキーマ別）/ C) 用途別（コアサービスは物理分離、運用系は論理分離）/ D) TBD | A) 各サービス専用DB（物理分離） | マイクロサービスの独立デプロイ・スケーリング原則を徹底。domain-analytics.md §7.8「マイクロサービスを基本構成として採用」に整合 |
| 19 | SVC-02（ポイント台帳）のデータストアはどれか | A) Azure SQL Database（リレーショナル、ACID保証）/ B) Azure Cosmos DB（NoSQL、グローバル分散）/ C) Azure SQL Database + Azure Cache for Redis（読み取り高速化） | C) Azure SQL Database + Redis | 台帳の整合性（ACID）はAzure SQLで保証し、残高照会の高頻度読み取り（P95 < 2s）はRedisキャッシュで対応 |
| 20 | Event Sourcing パターンの採用有無（domain-analytics.md §TBD-12に記載） | A) 採用（SVC-02の台帳設計にEvent Storeを使用）/ B) 不採用（通常CRUD + ドメインイベント発行）/ C) TBD（アーキテクチャ決定後） | C) TBD（アーキテクチャ決定後） | domain-analytics.md §TBD-12「Event Sourcing採用は実装複雑度とチーム習熟度に依存。未確定」と明記されている |
| 21 | SVC-06（CDP）向けのフィーチャーストア方式はどれか | A) Azure Machine Learning Feature Store / B) Azure Cache for Redis（特徴量キャッシュ）/ C) Azure Blob Storage + Parquet（バッチ特徴量）/ D) TBD（SVC-07との設計連携後） | D) TBD（SVC-07との設計連携後） | フィーチャーストアはSVC-06とSVC-07（AI/ML）の境界で議論が必要。Q15のホスティング選定（Azure ML採用可否）に依存 |
| 22 | サービス間通信の認証方式はどれか | A) Azure Managed Identity（シークレット不要、推奨）/ B) JWTサービストークン（短命トークン）/ C) mTLS（相互TLS）/ D) 混在（外部公開はMTLS、内部はManaged Identity） | A) Azure Managed Identity | Azure環境でのベストプラクティス。シークレット管理不要で最小権限を実現。domain-analytics.md §7.8「Azure有力」に整合 |
| 23 | SVC-15（認可チェック）の実装パターンはどれか | A) JWTクレームをアプリケーション層でローカル評価（軽量）/ B) 全サービスがSVC-15の/authz/check APIを呼び出す（中央集権）/ C) JWTクレームでシンプルな認可、複雑なポリシーのみSVC-15に委譲（ハイブリッド） | C) ハイブリッド（JWTクレーム + 複雑ポリシーはSVC-15委譲） | 軽量な認可（ロールチェック）はJWTクレームでローカル解決し、SVC-15への同期呼び出しによるレイテンシ増加を最小化 |
| 24 | 外部公開API向けゲートウェイの対象スコープはどれか（DEC-009参照） | A) 顧客向け（SVC-05）とパートナー向け（SVC-12）のみ / B) 全サービスに一律適用 / C) 顧客向けのみ（SVC-05） | A) 顧客向け + パートナー向け | DEC-009「APIゲートウェイは外部公開エンドポイントのみ設置」に基づく。内部BC間通信は直接通信 |
| 25 | ブロッカー#7（リアルタイムSLA未確定）の状態での設計進め方はどれか | A) UC別3段階SLA（<1秒/<5分/バッチ）を仮定して設計を開始し、確定後に修正 / B) SLA確定まで全サービスの詳細設計を待機 / C) バッチ前提で設計し、リアルタイム要件は後から追加 | A) UC別3段階SLA（仮定）で先行設計 | domain-analytics.md §9 ブロッカー#7「UC別3段階SLAで暫定合意」が推奨される次アクションとして示されている。設計の前進を優先 |
| 26 | ブロッカー#4（ランク制度設計）の状態での SVC-03（ルールエンジン）設計進め方はどれか | A) RankRule管理のインターフェース（API）のみ定義し、閾値・更新タイミングはTBDのまま設計開始 / B) ブロッカー解消まで待機 / C) ブロンズ/シルバー/ゴールド3ランクを仮定して設計開始 | A) インターフェースのみ定義して先行 | ランク閾値はビジネス要件だがAPIインターフェース（RankRule CRUD）は独立して設計可能。ブロッカー解消後に実装値を確定 |
| 27 | ブロッカー#3（名寄せキー）の状態でのSVC-06（CDP）設計進め方はどれか | A) 名寄せロジック以外（収集/品質監査/UCV格納）のインターフェースを先行設計 / B) ブロッカー解消まで待機 / C) 「メール+電話+会員番号」の複合キー確率マッチングを仮定して設計開始 | A) 名寄せロジック以外を先行設計 | データ収集パイプライン・UCV格納インターフェースは名寄せキー確定に依存しない。名寄せロジックはプラグイン設計で後から差し込む方式を採用 |
| 28 | ブロッカー#9（生成AIガードレール）の状態でのSVC-09（コンテンツ生成・承認）設計進め方はどれか | A) 承認ワークフロー（DRAFT→CHECKING→APPROVED→PUBLISHED）のインターフェースを先行設計し、ContentModerationServiceの実装はTBD / B) ブロッカー解消まで待機 / C) Azure Content Safety前提で設計を開始 | A) ワークフローI/Fを先行設計 | 承認フロー構造（ステートマシン）はガードレール内容に依存しない。モデレーション実装はDEC-012でTBDと明記されており分離可能 |
| 29 | 分散トレーシングの実装方式はどれか | A) Azure Application Insights SDK 直接組み込み / B) OpenTelemetry (OTel) + Azure Monitor エクスポーター / C) TBD | B) OpenTelemetry + Azure Monitor | OTel標準でベンダーロックインを回避しつつ、Azure Monitor/Application Insightsへ集約。将来的な基盤変更への柔軟性を確保 |
| 30 | サービス間の契約テスト（Consumer-Driven Contract Test）の採用可否はどれか | A) 採用（Pact等を使用し、サービス間APIの互換性を自動検証）/ B) 不採用（E2Eテストで代替）/ C) TBD（サービス詳細設計後に判断） | C) TBD（詳細設計後に判断） | サービス間I/Fが確定していない段階での採否判断は時期尚早。詳細設計（SVC-NN-description.md）が揃った段階で、I/Fの安定度・変更頻度を確認してから決定 |

---

## 回答方法

以下のいずれかを選択してください：

- **✅ 各質問に回答する**: 上記の質問にコメントで回答してください
- **🤖 Copilot の推論で進めてよい**: このコメントに「推論で進めてください」または「作業を進めてください」とリプライしてください。Copilot が利用可能な情報から推論して進行します。

> ⚠️ 推論で進める場合、不確実な箇所は `TBD（推論: {根拠}）` と明記し、その箇所に「この回答はCopilot推論をしたものです。」と補足します。

---

## 推論補完ログ

（推論で補完した場合のみ記録）
