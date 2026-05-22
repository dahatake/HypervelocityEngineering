# Sub-003 完了報告 — APIカタログ Table B 候補抽出

<!-- validation-confirmed -->
<!-- parent-task: Arch-ApplicationAnalytics/Issue-0 -->

## 目的

親 Step.1（Arch-ApplicationAnalytics）の SPLIT_REQUIRED により分割されたサブタスク Sub-003 を実行し、API カタログ Table B 候補を `docs/catalog/app-catalog.md` §7.1/§7.2 から抽出する。

## 変更点

- 新規作成: `work/Arch-Microservice-ServiceCatalog/Issue-0/sub-003/table-b-fragment.md`
  - Table B（9 列：API ID / API 名 / 所属サービス / エンドポイント / HTTP / 主要パラメータ / 主要レスポンス / SoT / 責務）に従い、API-B01〜API-B12 の 12 行を抽出。
  - エンドポイント・HTTP は原典に明示がないため全行 `TBD` とし、API 名は「資料上の処理/連携名」を出典付きで記載（AC 準拠）。
  - SoT 一貫性チェック表を併記（§7.1 と整合）。
- 新規作成: 本完了報告ファイル。

## 影響範囲

- 後続: Arch-Microservice-ServiceCatalog（API 行の正式登録）／Arch-Microservice-ServiceDetail（エンドポイント・スキーマ確定）。
- 既存ドキュメントへの変更なし（追記のみ、`docs/`・`knowledge/` は未変更）。

## 検証

- 検証マーカー: 本ファイル冒頭に `<!-- validation-confirmed -->` を記載済み。
- AC 検証:
  - [x] `docs/catalog/app-catalog.md` §7.2 主要連携カタログ（11 行）を漏れなく Table B に反映（API-B01〜API-B12、複数 To 行は分割せず責務列に記載）。
  - [x] エンドポイント・HTTP メソッドが原典に明示されない場合は `TBD` と明記（全 12 行）。
  - [x] API 名は資料上の処理/連携名で記載し、§7.1/§7.2 の出典行を「出典」列に明示。
  - [x] 出力ファイルパス `work/Arch-Microservice-ServiceCatalog/Issue-0/sub-003/table-b-fragment.md` に保存。
- 静的検証: 出力 Markdown を view で再読込し、テーブル列数（9 列 + 出典 = 10 列）と API ID 連番（B01〜B12）を確認。
- ビルド/Lint/Test: 本サブタスクは設計ドキュメント抽出のため該当なし（理由: 文書のみの追加、コード変更なし）。

## 既知の制約

- Sub-001 / Sub-002（Table A 断片）が本実行時点で未生成。所属サービス列は `app-catalog.md` §7.1 の Primary APP のみを根拠とし、Table A 完成後の再突合を Sub-001/002 完了後の後続タスクに委ねる（`table-b-fragment.md` §4 に明記）。
- エンドポイント URL・HTTP メソッド・要求/応答スキーマは全行 TBD（原典に記述なし）。
- 「KPI 集計データ・実験ログ配信」（API-B11）は配信先（APP-04/06/02）ごとに分解の余地あり（後続工程判断）。

## 次にやるサブタスク

- Sub-001 / Sub-002 完了後、Table A（サービス・画面）と Table B（API）の所属サービス列突合を行う差分タスク。
- Arch-Microservice-ServiceDetail にて Table B の各 API のエンドポイント・スキーマを確定。
- 外部境界（配信ゲートウェイ／決済・会計／提携 API／既存 IdP）の API 仕様調達。

## status / summary / next_actions / artifacts

- status: done
- summary: app-catalog.md §7.1/§7.2 から API 候補 12 行（API-B01〜B12）を Table B 形式で抽出し、`work/Arch-Microservice-ServiceCatalog/Issue-0/sub-003/table-b-fragment.md` に保存した。エンドポイント・HTTP は全行 TBD。
- next_actions:
  1. Sub-001/Sub-002 完了後、Table A との所属サービス列突合
  2. Arch-Microservice-ServiceDetail でエンドポイント/スキーマ確定
  3. 外部境界 API 仕様の調達
- artifacts:
  - `work/Arch-Microservice-ServiceCatalog/Issue-0/sub-003/table-b-fragment.md`
  - `work/Arch-ApplicationAnalytics/Issue-0/sub-003/completion-report.md`
