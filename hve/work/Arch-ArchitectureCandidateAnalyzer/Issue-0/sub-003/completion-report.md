# Sub-003 完了報告 — APIカタログTableB候補抽出

<!-- parent-task: Arch-ArchitectureCandidateAnalyzer/Issue-0 sub-003 -->
<!-- validation-confirmed -->

- status: done
- summary: `docs/catalog/app-catalog.md` §7.1/§7.2 と `docs/catalog/use-case-catalog.md` §3 を一次根拠として、Table B（API カタログ）候補 12 行（API-B01〜API-B12）を抽出し、`work/Arch-Microservice-ServiceCatalog/Issue-0/sub-003/table-b-fragment.md` に保存済み。
- next_actions:
  - Sub-001 / Sub-002（Table A 断片：サービス/画面）成果物の生成後に所属サービス列を再突合する。
  - 後続 Arch-Microservice-ServiceCatalog / ServiceDetail 工程でエンドポイント・HTTP メソッド・スキーマを確定する。
- artifacts:
  - `work/Arch-Microservice-ServiceCatalog/Issue-0/sub-003/table-b-fragment.md`（API 候補 12 行 + SoT 整合チェック）
  - `work/Arch-ArchitectureCandidateAnalyzer/Issue-0/sub-003/completion-report.md`（本ファイル）

## 目的

親 Step.2（Arch-ArchitectureCandidateAnalyzer）の SPLIT_REQUIRED 判定で分割された Sub-003 として、API カタログ（Table B）候補の単独責務抽出を完遂する。

## 変更点

- 新規: `work/Arch-Microservice-ServiceCatalog/Issue-0/sub-003/table-b-fragment.md`（既存生成済み、本サブタスクで再確認）
  - Table B 12 行（API-B01〜API-B12）: API ID / API 名 / 所属サービス / エンドポイント / HTTP / 主要パラメータ / 主要レスポンス / SoT / 責務 / 出典
  - SoT 一貫性チェック表（§7.1 整合確認）
  - 残課題 / TBD セクション
- 新規: 本完了報告

## 影響範囲

- `work/Arch-Microservice-ServiceCatalog/Issue-0/sub-003/` 配下のみ（成果物書き込み先）
- `work/Arch-ArchitectureCandidateAnalyzer/Issue-0/sub-003/` 配下のみ（完了報告書き込み先）
- 既存コード・他 Issue 成果物への変更なし

## 検証結果

### 検証

1. **AC 充足確認**
   - AC1（§7.2 主要連携カタログから API 候補抽出）: 充足。§7.2 全 11 行 + APP-12（不正検知）を反映し、API-B01〜API-B12 を抽出。
   - AC2（エンドポイント・HTTP 未明示時は TBD、API 名は資料上の処理/連携名で出典付き）: 充足。全 12 行で `エンドポイント=TBD`、`HTTP=TBD（同期/event/api/batch）` を併記し、API 名は §7.2 のデータ/イベント・トリガ列から採用、行ごとに出典列（例: `app-catalog.md §7.2 行N, §7.1 ドメイン名`）を明記。
   - AC3（保存先 `work/Arch-Microservice-ServiceCatalog/Issue-0/sub-003/table-b-fragment.md`）: 充足。8,308 bytes で存在確認済み。
2. **SoT 整合**: Table B の SoT 列を §7.1 SoR/責務境界の Primary APP/書込権限と突合し、12 行とも整合（fragment §3 参照）。
3. **捏造チェック**: API 名・SoT・所属サービスは全行 §7.1/§7.2/§3 のいずれかに直接出典あり。エンドポイント/HTTP/スキーマは推測せず TBD のまま据え置き。
4. **静的検証**: Markdown 表記（パイプ表整合、見出し階層）を目視確認済み。

### 既知の制約

- Sub-001 / Sub-002（Table A 断片）が本サブタスク実行時点で生成されていないため、所属サービス列の最終突合は後続で実施する必要がある（fragment §4 残課題に明記）。
- エンドポイント URL・HTTP メソッド・要求/応答スキーマは原典に記載がなく全行 TBD。後続 Arch-Microservice-ServiceCatalog/ServiceDetail 工程で確定する。
- 配信ゲートウェイ・決済/会計・提携先 API・既存 IdP は外部境界。仕様詳細は別途調達/契約資料を要参照。

## 次にやるサブタスク

- Sub-001/002 完了後の Table A × Table B 突合（所属サービス整合再確認）
- Arch-Microservice-ServiceCatalog 工程でのエンドポイント・HTTP・スキーマ確定
- API-B11（KPI 集計データ・実験ログ配信）の配信先別 API 分解検討
