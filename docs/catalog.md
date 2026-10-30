# カタログ

既存の機能・API・テーブル・共通部品の対応表です。1 行 1 項目の短い表にし、詳細はリンク先のファイルに任せます。
機能の表は rd-author（要求 ID・題名・決定状態）と implementer（実装ファイル・テスト・共通部品）が更新します。
未実装の要求は、実装ファイルとテストの欄を「未実装」とします。

run 清掃は結果が全件完了で main へ統合後、その main 上の verify と清掃前 run-report の確定に成功した後だけ実行します。それ以外の run は自動期限なく保持します。

## 機能

| 要求 ID | 題名 | 決定状態 | 実装ファイル | テスト | 使っている共通部品 |
|---|---|---|---|---|---|
| FR-1009 | 正常完了 run の統合後清掃 | 承認済み（依頼 2026-10-10） | `scripts/clean-work.py`、[`.github/agents/conductor.agent.md`](docs/../.github/agents/conductor.agent.md) | `tests/toolkit/test_clean_work.py`、`tests/toolkit/test_run_state.py`、`tests/system/e2e/test_run_owned_cleanup.py`、`tests/system/test_run_cleanup_system.py` | run 作業資産清掃、worktree pool 管理、conductor 終了契約 |
| FR-1010 | 清掃の診断と再開 | 承認済み（依頼 2026-10-10） | `scripts/clean-work.py`、[`.github/agents/conductor.agent.md`](docs/../.github/agents/conductor.agent.md)、`users-guide/02-during-and-after-run.md`、`users-guide/05-scripts-reference.md`、`users-guide/07-troubleshooting.md` | `tests/toolkit/test_clean_work.py`、`tests/system/e2e/test_run_owned_cleanup.py`、`tests/system/test_run_cleanup_system.py` | run 状態・完了記録、run 作業資産清掃、conductor 終了契約、run 運用ガイド |
| NFR-OPS-005 | 所有権と保護状態にもとづく安全な削除 | 承認済み（依頼 2026-10-10） | `scripts/clean-work.py` | `tests/toolkit/test_clean_work.py`、`tests/toolkit/test_run_state.py`、`tests/system/e2e/test_run_owned_cleanup.py`、`tests/system/test_run_cleanup_system.py` | run 作業資産清掃、run 状態・完了記録、worktree pool 管理 |
| NFR-COMPAT-001 | Windows・報告・配布文書の一貫性 | 承認済み（依頼 2026-10-10） | `scripts/clean-work.py`、`tools/install.py`、[`.github/agents/conductor.agent.md`](docs/../.github/agents/conductor.agent.md)、`users-guide/02-during-and-after-run.md`、`users-guide/05-scripts-reference.md`、`users-guide/07-troubleshooting.md` | `tests/toolkit/test_clean_work.py`、`tests/system/e2e/test_run_owned_cleanup.py`、`tests/system/test_run_cleanup_system.py` | run 作業資産清掃、run 状態・完了記録、worktree pool 管理、conductor 終了契約、run 運用ガイド、配布同期対象 |
| FR-1017 | データ層の妥当性検査の自動実行 | 承認済み（依頼 2026-10-14） | [`.github/workflows/ebak-data-layer.yml`](docs/../.github/workflows/ebak-data-layer.yml) | `tests/system/test_data_layer_workflow_system.py` | データ層検査、配布同期対象 |
| FR-1018 | 不整合の自動修復と修復の反映 | 承認済み（依頼 2026-10-14） | [`.github/workflows/ebak-data-layer.yml`](docs/../.github/workflows/ebak-data-layer.yml) | `tests/system/test_data_layer_workflow_system.py` | データ層修復、データ層検査 |
| FR-1019 | 直せない不整合の Issue 化 | 承認済み（依頼 2026-10-14） | [`.github/workflows/ebak-data-layer.yml`](docs/../.github/workflows/ebak-data-layer.yml) | `tests/system/test_data_layer_workflow_system.py` | データ層修復 |
| NFR-SEC-004 | データ層ワークフローの最小権限と書き込みの安全性 | 承認済み（依頼 2026-10-14） | [`.github/workflows/ebak-data-layer.yml`](docs/../.github/workflows/ebak-data-layer.yml) | `tests/system/test_data_layer_workflow_system.py` | 配布同期対象 |
| NFR-OPS-006 | データ層ワークフローの配布と利用者向け文書 | 承認済み（依頼 2026-10-14） | [`.github/workflows/ebak-data-layer.yml`](docs/../.github/workflows/ebak-data-layer.yml)、`tools/install.py`、`README.md`、`users-guide/04-customization.md` | `tests/toolkit/test_install.py`、`tests/system/test_data_layer_workflow_system.py` | 配布同期対象 |
| FR-1044 | データ層の確認・修復の共通の入口 | 承認済み（包括承認 2026-10-16・approval_policy） | [`.github/workflows/ebak-data-layer.yml`](docs/../.github/workflows/ebak-data-layer.yml)、`tools/install.py`、`scripts/rdfix.py` | `tests/toolkit/test_repair_entrypoints.py`、`tests/integration/test_repair_entrypoints_it.py`、`tests/system/test_data_layer_repair_system.py` | データ層修復、データ層検査 |
| FR-1045 | インストール時のデータ層の確認と自動修復 | 承認済み（依頼 2026-10-16） | `tools/install.py` | `tests/toolkit/test_repair_entrypoints.py`、`tests/integration/test_repair_entrypoints_it.py`、`tests/system/test_data_layer_repair_system.py` | データ層修復、配布同期対象 |
| FR-1046 | 手動のデータ層の確認と修復のコマンド | 承認済み（依頼 2026-10-16） | `scripts/rdfix.py`、`scripts/verify.py`、`users-guide/05-scripts-reference.md` | `tests/system/test_data_layer_repair_system.py`、`tests/toolkit/test_rdfix_full.py`、`tests/integration/test_data_layer_repair.py` | データ層修復、データ層検査 |
| NFR-REL-002 | 自動修復の安全性（要求定義書の保護・書き込みの原子性・取り消し） | 承認済み（包括承認 2026-10-16・approval_policy） | `scripts/rdfix.py` | `tests/toolkit/test_rdfix_full.py`、`tests/integration/test_data_layer_repair.py`、`tests/system/test_data_layer_repair_system.py` | データ層修復 |
| NFR-REL-003 | 自動修復の冪等性・収束・排他 | 承認済み（包括承認 2026-10-16・approval_policy） | `scripts/rdfix.py` | `tests/toolkit/test_rdfix_full.py`、`tests/integration/test_data_layer_repair.py` | データ層修復 |
| NFR-REL-004 | 壊れた入力と git でないディレクトリでの確認・修復 | 承認済み（包括承認 2026-10-16・approval_policy） | `scripts/rdfix.py`、`scripts/ebaklib.py` | `tests/toolkit/test_rdfix_robust.py`、`tests/integration/test_data_layer_repair.py` | データ層修復 |
| NFR-PERF-005 | データ層の確認・修復の速さ | 承認済み（依頼 2026-10-16） | `scripts/rdfix.py`、`scripts/ebaklib.py` | `tests/toolkit/test_rdfix_robust.py`、`tests/integration/test_data_layer_repair.py` | データ層修復、データ層検査 |
| NFR-COMPAT-004 | 既存のデータ層の検査・修復の挙動の維持 | 承認済み（包括承認 2026-10-16・approval_policy） | `scripts/rdfix.py`、[`.github/workflows/ebak-data-layer.yml`](docs/../.github/workflows/ebak-data-layer.yml) | `tests/toolkit/test_repair_entrypoints.py`、`tests/integration/test_repair_entrypoints_it.py`、`tests/toolkit/test_rdfix.py`、`tests/system/test_data_layer_workflow_system.py` | データ層修復 |
| NFR-OPS-007 | データ層の確認・修復の配布と利用者向け文書 | 承認済み（包括承認 2026-10-16・approval_policy） | `tools/install.py`、`scripts/ebaklib.py`、`README.md`、`CHANGELOG.md`、`users-guide/04-customization.md`、`users-guide/05-scripts-reference.md`、`users-guide/06-quality-gates.md`、`users-guide/07-troubleshooting.md`、[`.github/agents/conductor.agent.md`](docs/../.github/agents/conductor.agent.md) | `tests/toolkit/test_repair_entrypoints.py`、`tests/integration/test_repair_entrypoints_it.py`、`tests/toolkit/test_version.py` | 配布同期対象 |
| NFR-COR-001 | 再現性 | 廃止 | 未実装 | 未実装 | なし |
| NFR-COR-002 | エラーの明確性 | 廃止 | 未実装 | 未実装 | なし |
| NFR-COR-003 | 境界値 | 廃止 | 未実装 | 未実装 | なし |
| NFR-COR-004 | データ保全 | 廃止 | 未実装 | 未実装 | なし |
| NFR-COR-005 | 文書化 | 廃止 | 未実装 | 未実装 | なし |
| NFR-PERF-001 | 公開データセットの処理性能 | 廃止 | 未実装 | 未実装 | なし |
| NFR-PERF-002 | 大規模性能 | 廃止 | 未実装 | 未実装 | なし |
| NFR-REL-001 | 検証による完了判定 | 廃止 | 未実装 | 未実装 | なし |
| FR-1011 | 2D マップのノード選択と強調 | 承認済み | `EABK-Studio/web/js/map2d.js` | `tests/system/e2e/test_studio_map_placement_system.py`, `EABK-Studio/tests/test_studio.py` | ストア |
| FR-1012 | 実装配置図（画面・API・データの 3 層） | 承認済み | `EABK-Studio/web/js/diagrams.js`, `EABK-Studio/web/js/i18n.js` | `tests/system/e2e/test_studio_map_placement_system.py`, `EABK-Studio/tests/test_studio.py` | ストア、UI 部品、デザイン基盤 |
| FR-1013 | データの ER 図表示 | 承認済み | `EABK-Studio/web/js/insights.js`, `EABK-Studio/web/js/diagrams.js`, `EABK-Studio/web/js/i18n.js` | `EABK-Studio/tests/test_studio.py` | 管理データモデル、ストア、UI 部品、デザイン基盤 |
| NFR-PERF-003 | EABK toolkit の子プロセス・ブラウザー起動の削減 | 承認済み | `scripts/ebaklib.py`、`scripts/rdcheck.py`、`scripts/rdfix.py`、`scripts/ledger.py` | `tests/toolkit/test_git_perf.py`、`tests/toolkit/test_speed.py`、`tests/toolkit/test_select_changed.py` | git ls-files 並行取得、System Test の選択 |
| NFR-COMPAT-002 | 性能改善による挙動の不変 | 承認済み | `scripts/ebaklib.py`、`scripts/rdcheck.py`、`scripts/rdfix.py` | `tests/toolkit/test_git_perf.py` | git ls-files 並行取得 |
| FR-1014 | 要求の実装状態ビュー（実装の登録と試験 pass の区別） | 承認済み | `EABK-Studio/eabk_model.py`, `EABK-Studio/web/js/implstatus.js`, `EABK-Studio/web/js/app.js`, `EABK-Studio/web/js/i18n.js`, `users-guide/studio/08-data-reference.md` | `tests/system/e2e/test_impl_status_system.py`, `EABK-Studio/tests/test_studio.py` | 管理データモデル、ストア、UI 部品、デザイン基盤 |
| FR-1015 | 次に実装すべき要求の分析コマンド | 承認済み | `scripts/next-impl.py`、`tools/install.py`、`users-guide/05-scripts-reference.md` | `tests/toolkit/test_next_impl.py` | 次実装候補の分析、run 状態・完了記録、配布同期対象 |
| FR-1016 | 許容時間を指定するだけの実装依頼（/build 入口）の生成 | 承認済み | `scripts/build-request.py`、[`.github/skills/build/SKILL.md`](docs/../.github/skills/build/SKILL.md)、`tools/install.py`、`users-guide/05-scripts-reference.md` | `tests/toolkit/test_next_impl.py`、`tests/system/e2e/test_build_request_system.py` | 次実装候補の分析、run 状態・完了記録、配布同期対象 |
| FR-1020 | エンティティ台帳の導出（既存の構造化欄が正本） | 承認済み | `scripts/entities.py`、`scripts/rdcheck.py`、`tools/install.py`、`users-guide/05-scripts-reference.md` | `tests/toolkit/test_entities.py` | エンティティ台帳・企業カタログ照合 |
| FR-1021 | エンティティ × ユースケース の対応表（Studio） | 承認済み | `EABK-Studio/eabk_model.py`, `EABK-Studio/web/js/entities.js`, `EABK-Studio/web/js/app.js`, `EABK-Studio/web/js/i18n.js`, `EABK-Studio/web/js/ui.js`, `EABK-Studio/web/app.css`, `EABK-Studio/README.md`, `users-guide/studio/02-screens.md` | `tests/system/e2e/test_entities_studio_system.py`, `EABK-Studio/tests/test_studio.py` | エンティティ台帳・企業カタログ照合、管理データモデル、ストア、UI 部品、デザイン基盤 |
| FR-1022 | エンティティ詳細（要求・テーブル・コンポーネント） | 承認済み | `EABK-Studio/eabk_model.py`, `EABK-Studio/web/js/entities.js`, `EABK-Studio/web/js/drawer.js`, `EABK-Studio/web/js/i18n.js`, `EABK-Studio/web/app.css` | `tests/system/e2e/test_entities_studio_system.py`, `EABK-Studio/tests/test_studio.py` | エンティティ台帳・企業カタログ照合、管理データモデル、ストア、UI 部品、デザイン基盤 |
| FR-1023 | 企業データカタログとの整合の検査 | 承認済み | `scripts/entities.py`、`scripts/rdcheck.py`、`tools/install.py`、`users-guide/05-scripts-reference.md` | `tests/toolkit/test_entities.py` | エンティティ台帳・企業カタログ照合 |
| FR-1024 | 企業データカタログが覆わないエンティティの ToDo 生成 | 承認済み | `scripts/entities.py`、`scripts/rdcheck.py`、`tools/install.py`、`users-guide/05-scripts-reference.md` | `tests/toolkit/test_entities.py` | エンティティ台帳・企業カタログ照合 |
| NFR-COMPAT-003 | エンティティ機能の他リポジトリでの動作 | 承認済み | `scripts/entities.py`、`scripts/rdcheck.py`、`tools/install.py`、`users-guide/05-scripts-reference.md`、`EABK-Studio/eabk_model.py`、`EABK-Studio/web/js/entities.js` | `tests/toolkit/test_entities.py`、`tests/system/e2e/test_entities_studio_system.py`、`EABK-Studio/tests/test_studio.py` | エンティティ台帳・企業カタログ照合、管理データモデル |
| NFR-SEC-023 | 企業データカタログの参照の安全性 | 承認待ち | `scripts/entities.py` | `tests/toolkit/test_entities.py` | エンティティ台帳・企業カタログ照合 |
| FR-1025 | 列（属性）の任意欄（カタログのテーブル節） | 承認済み | `scripts/entities.py`、`scripts/rdcheck.py`、`EABK-Studio/eabk_model.py`、`users-guide/03-requirements-format.md`、`users-guide/05-scripts-reference.md` | `tests/integration/test_entity_columns.py`、`EABK-Studio/tests/test_studio.py` | エンティティ台帳・企業カタログ照合、管理データモデル |
| FR-1026 | エンティティ間・列間の関係と、要求・テーブル・コンポーネントとの関係 | 承認済み | `scripts/entities.py`、`scripts/rdcheck.py`、`EABK-Studio/eabk_model.py`、`users-guide/03-requirements-format.md`、`users-guide/05-scripts-reference.md` | `tests/integration/test_entity_columns.py`、`EABK-Studio/tests/test_studio.py` | エンティティ台帳・企業カタログ照合、管理データモデル |
| FR-1027 | 意味的ズーム（2D・3D 共通の規則） | 承認済み | `EABK-Studio/web/js/semzoom.js`、`EABK-Studio/web/js/sz2d.js`、`EABK-Studio/web/js/sz3d.js`、`EABK-Studio/web/js/entities.js`、`EABK-Studio/web/js/map2d.js`、`EABK-Studio/web/js/map3d.js`、`EABK-Studio/web/js/i18n.js`、`EABK-Studio/web/sz.css`、`EABK-Studio/web/index.html`、`EABK-Studio/README.md`、`users-guide/studio/02-screens.md` | `tests/system/e2e/test_semantic_zoom_system.py`、`tests/integration/test_semantic_zoom_ui.py`、`EABK-Studio/tests/test_semantic_zoom_wiring.py`、`EABK-Studio/tests/test_studio.py` | 管理データモデル、ストア、UI 部品、意味的ズーム |
| FR-1028 | 2D での関係と列の表現 | 承認済み | `EABK-Studio/web/js/sz2d.js`、`EABK-Studio/web/js/semzoom.js`、`EABK-Studio/web/js/map2d.js`、`EABK-Studio/web/js/entities.js`、`EABK-Studio/web/sz.css` | `tests/system/e2e/test_semantic_zoom_system.py`、`tests/integration/test_semantic_zoom_ui.py` | 管理データモデル、UI 部品、意味的ズーム |
| FR-1029 | 3D での関係と列の表現 | 承認済み | `EABK-Studio/web/js/sz3d.js`、`EABK-Studio/web/js/semzoom.js`、`EABK-Studio/web/js/map3d.js`、`EABK-Studio/web/sz.css` | `tests/system/e2e/test_semantic_zoom_system.py`、`tests/integration/test_semantic_zoom_ui.py` | 管理データモデル、ストア、意味的ズーム |
| FR-1030 | DDL・スキーマファイルからの列と関係の補完（任意の拡張） | 承認済み | `scripts/entities.py`、`users-guide/03-requirements-format.md` | `tests/integration/test_entity_columns.py` | エンティティ台帳・企業カタログ照合 |
| FR-1031 | 表示オブジェクトへのリンク | 承認済み | `EABK-Studio/web/js/xref.js`, `EABK-Studio/web/js/app.js`, `EABK-Studio/web/js/implstatus.js`, `EABK-Studio/web/js/insights.js`, `EABK-Studio/web/js/map2d.js`, `EABK-Studio/web/app.css` | `tests/system/e2e/test_studio_links_wrap_status_arch_system.py`, `EABK-Studio/tests/test_links_wrap_status_ui.py`, `EABK-Studio/tests/test_links_wrap_status_ui2.py` | UI 部品、ストア |
| FR-1032 | 設計・開発履歴と進捗の項目の自動折り返し | 承認済み | `EABK-Studio/web/js/insights.js`, `EABK-Studio/web/app.css` | `tests/system/e2e/test_studio_links_wrap_status_arch_system.py`, `EABK-Studio/tests/test_links_wrap_status_ui.py`, `EABK-Studio/tests/test_links_wrap_status_ui2.py` | デザイン基盤 |
| FR-1033 | 実装状態のグラフ区間からの画面横断の強調と絞り込み | 承認済み | `EABK-Studio/web/js/implstatus.js`, `EABK-Studio/web/js/i18n.js`, `EABK-Studio/web/app.css` | `tests/system/e2e/test_studio_links_wrap_status_arch_system.py`, `EABK-Studio/tests/test_links_wrap_status_ui.py`, `EABK-Studio/tests/test_links_wrap_status_ui2.py` | ストア、UI 部品 |
| FR-1061 | 実装状態のガントチャート図ビュー | 承認済み | `EABK-Studio/eabk_model.py`, `EABK-Studio/web/js/implstatus.js`, `EABK-Studio/web/js/i18n.js`, `EABK-Studio/web/app.css` | `tests/system/e2e/test_impl_gantt_system.py`, `EABK-Studio/tests/test_studio.py` | 管理データモデル、ストア、UI 部品 |
| FR-1034 | アーキテクチャ図とエンティティモデル図（2D/3D）とデータの所在 | 承認済み | `EABK-Studio/eabk_model.py`, `EABK-Studio/web/js/semzoom.js`, `EABK-Studio/web/js/sz2d.js`, `EABK-Studio/web/js/map2d.js`, `EABK-Studio/web/js/map3d.js`, `EABK-Studio/web/js/i18n.js` | `tests/system/e2e/test_studio_links_wrap_status_arch_system.py`, `EABK-Studio/tests/test_arch_diagram.py`, `EABK-Studio/tests/test_req_placement.py` | 管理データモデル、ストア、意味的ズーム |
| NFR-PERF-004 | エンティティ表示の大規模データでの滑らかさ | 承認済み | `EABK-Studio/web/js/semzoom.js`、`EABK-Studio/web/js/sz2d.js`、`EABK-Studio/web/js/sz3d.js`、`scripts/entities.py` | `tests/system/e2e/test_semantic_zoom_system.py`、`tests/integration/test_semantic_zoom_ui.py` | 意味的ズーム |
| NFR-UX-010 | エンティティ表示の代替手段・キーボード・言語 | 承認済み | `EABK-Studio/web/js/semzoom.js`、`EABK-Studio/web/js/sz2d.js`、`EABK-Studio/web/js/sz3d.js`、`EABK-Studio/web/js/i18n.js`、`EABK-Studio/web/sz.css` | `tests/system/e2e/test_semantic_zoom_system.py`、`tests/integration/test_semantic_zoom_ui.py` | 意味的ズーム、UI 部品 |
| FR-1035 | 外部連携カタログ（データ層） | 承認済み | `scripts/ebaklib.py`、`scripts/rdcheck.py`、`tools/templates/docs/integrations.md` | `tests/toolkit/test_integrations.py`、`tests/integration/test_external_integrations.py` | 外部連携カタログ解析・検査 |
| FR-1036 | 外部連携カタログの ID 採番と整合検査 | 承認済み | `scripts/next-id.py`、`scripts/rdcheck.py`、`scripts/ebaklib.py`、`.github/skills/requirement-definition/integration-checklist.md` | `tests/toolkit/test_integrations.py`、`tests/integration/test_external_integrations.py` | 外部連携カタログ解析・検査 |
| FR-1037 | 外部連携カタログの配布と管理手順の文書化 | 承認済み | `tools/install.py`、`tools/templates/docs/integrations.md`、`.github/skills/requirement-definition/integration-checklist.md`、`scripts/ebaklib.py`、`users-guide/03-requirements-format.md`、`users-guide/05-scripts-reference.md`、`users-guide/11-integration-catalog.md`、`README.md`、`CHANGELOG.md` | `tests/toolkit/test_integrations.py`、`tests/integration/test_external_integrations.py`、`tests/system/test_integration_catalog_install_system.py`、`tests/toolkit/test_version.py` | 配布同期対象、外部連携カタログ解析・検査 |
| FR-1038 | 外部連携の要求チェックリストと要求のテンプレート | 承認済み | `.github/skills/requirement-definition/integration-requirements.md`、`tools/install.py`、`users-guide/11-integration-catalog.md` | `tests/toolkit/test_integration_requirements.py`、`tests/integration/test_external_integrations.py` | 配布同期対象 |
| FR-1039 | rd-author の手順への外部連携チェックの組込み | 承認済み | `.github/skills/requirement-definition/SKILL.md`、`.github/skills/rd-audit/SKILL.md`、`.github/skills/requirement-definition/integration-requirements.md`、`tools/install.py` | `tests/toolkit/test_integration_requirements.py`、`tests/integration/test_external_integrations.py` | 配布同期対象 |
| FR-1053 | マップの表示モード「RPG 風」 | 承認済み（依頼 2026-10-17） | `EABK-Studio/web/js/maprpg.js`、`EABK-Studio/web/js/rpgworld.js`、`EABK-Studio/web/js/rpgaudio.js`、`EABK-Studio/web/rpg.css`、`EABK-Studio/web/js/app.js`、`EABK-Studio/web/js/dim.js`、`EABK-Studio/web/js/i18n.js`、`EABK-Studio/web/index.html` | `EABK-Studio/tests/test_rpg_mode_ui.py`、`tests/system/e2e/test_studio_rpg_system.py` | 意味的ズーム、2D・3D 切替、RPG 風マップ |
| FR-1054 | RPG 風の音楽・効果音・キャラクターの生成 | 承認済み（依頼 2026-10-17） | docs/rpg-originality.md、`EABK-Studio/web/js/maprpg.js`、`EABK-Studio/web/js/rpgworld.js`、`EABK-Studio/web/js/rpgaudio.js`、`EABK-Studio/web/rpg.css`、`EABK-Studio/web/js/app.js`、`EABK-Studio/web/js/dim.js`、`EABK-Studio/web/js/i18n.js`、`EABK-Studio/web/index.html` | `EABK-Studio/tests/test_rpg_mode_ui.py`、`tests/system/e2e/test_studio_rpg_system.py` | 意味的ズーム、2D・3D 切替、RPG 風マップ |
| FR-1055 | RPG 風のファミコン風の操作 | 承認済み（依頼 2026-10-17） | `EABK-Studio/web/js/maprpg.js`、`EABK-Studio/web/js/rpgworld.js`、`EABK-Studio/web/js/rpgaudio.js`、`EABK-Studio/web/rpg.css`、`EABK-Studio/web/js/app.js`、`EABK-Studio/web/js/dim.js`、`EABK-Studio/web/js/i18n.js`、`EABK-Studio/web/index.html` | `EABK-Studio/tests/test_rpg_mode_ui.py`、`tests/system/e2e/test_studio_rpg_system.py` | 意味的ズーム、2D・3D 切替、RPG 風マップ |
| NFR-UX-012 | RPG 風の表示モードの動き・キーボード・性能・外部通信 | 承認済み（包括承認 2026-10-17・approval_policy） | `EABK-Studio/web/js/maprpg.js`、`EABK-Studio/web/js/rpgworld.js`、`EABK-Studio/web/js/rpgaudio.js`、`EABK-Studio/web/rpg.css`、`EABK-Studio/web/js/app.js`、`EABK-Studio/web/js/dim.js`、`EABK-Studio/web/js/i18n.js`、`EABK-Studio/web/index.html` | `EABK-Studio/tests/test_rpg_mode_ui.py`、`tests/system/e2e/test_studio_rpg_system.py` | RPG 風マップ |
| FR-1040 | 図式の各表示の 2D/3D 選択 | 承認済み | `EABK-Studio/web/js/dim.js`, `EABK-Studio/web/js/dgm3d.js`, `EABK-Studio/web/js/diagrams.js`, `EABK-Studio/web/js/app.js`, `EABK-Studio/web/js/i18n.js`, `EABK-Studio/web/app.css`, `EABK-Studio/README.md`, `users-guide/studio/02-screens.md` | `EABK-Studio/tests/test_nav_dims_ui.py`, `tests/system/e2e/test_studio_nav_dims_integrations_system.py` | ストア、UI 部品、デザイン基盤、Three.js 同梱モジュール、2D・3D 切替 |
| FR-1041 | ナビゲーションの MECE 化と各項目の説明 | 承認済み | `EABK-Studio/web/js/app.js`, `EABK-Studio/web/js/dim.js`, `EABK-Studio/web/js/i18n.js`, `EABK-Studio/web/js/ui.js`, `EABK-Studio/web/index.html`, `EABK-Studio/web/app.css`, `EABK-Studio/README.md`, `users-guide/studio/02-screens.md` | `EABK-Studio/tests/test_nav_dims_ui.py`, `tests/system/e2e/test_studio_nav_dims_integrations_system.py` | ストア、UI 部品、デザイン基盤、2D・3D 切替 |
| FR-1042 | 外部連携カタログの閲覧（Studio） | 承認済み | `EABK-Studio/web/js/integrations.js`, `EABK-Studio/eabk_model.py`, `EABK-Studio/web/js/drawer.js`, `EABK-Studio/web/js/diagrams.js`, `EABK-Studio/web/js/app.js`, `EABK-Studio/web/js/i18n.js`, `EABK-Studio/web/js/ui.js`, `EABK-Studio/web/js/xref.js` | `EABK-Studio/tests/test_integrations_catalog.py`, `EABK-Studio/tests/test_nav_dims_ui.py`, `tests/system/e2e/test_studio_nav_dims_integrations_system.py` | 管理データモデル、ストア、UI 部品、デザイン基盤 |
| FR-1047 | デザイントークン基盤とテーマ | 承認済み | `EABK-Studio/web/tokens.css`、`EABK-Studio/web/app.css`、`EABK-Studio/web/sz.css`、`EABK-Studio/web/js/theme.js`、`EABK-Studio/web/index.html`、`EABK-Studio/web/js/app.js` | `EABK-Studio/tests/test_design_tokens.py`、`tests/system/e2e/test_studio_fluent_appearance_system.py` | デザイン基盤、UI 部品 |
| FR-1048 | 主要画面の外観・部品・モーション・状態表現 | 承認済み | `EABK-Studio/web/tokens.css`、`EABK-Studio/web/app.css`、`EABK-Studio/web/js/ui.js`、`EABK-Studio/web/js/app.js`、`EABK-Studio/web/js/dim.js`、`EABK-Studio/web/js/dashboard.js`、`EABK-Studio/web/js/i18n.js` | `EABK-Studio/tests/test_fluent_look.py`、`tests/system/e2e/test_studio_fluent_appearance_system.py` | デザイン基盤、UI 部品 |
| NFR-A11Y-001 | 外観のアクセシビリティ（Fluent 2・WCAG 2.2 AA） | 承認済み | `EABK-Studio/web/tokens.css`、`EABK-Studio/web/app.css`、`EABK-Studio/web/js/ui.js`、`EABK-Studio/web/js/app.js` | `EABK-Studio/tests/test_design_tokens.py`、`tests/system/e2e/test_studio_fluent_appearance_system.py` | デザイン基盤、UI 部品 |
| NFR-PERF-006 | 外観の変更による描画性能と既存挙動の維持 | 承認済み | `EABK-Studio/web/js/ui.js`、`EABK-Studio/web/app.css` | `EABK-Studio/tests/test_fluent_look.py`、`tests/system/e2e/test_studio_fluent_appearance_system.py` | デザイン基盤、UI 部品 |
| FR-1057 |  要求の階層化（目的→領域→要求） | 承認済み | `scripts/metadata.json`、`scripts/ebaklib.py`、`scripts/rdcheck.py`、`EABK-Studio/eabk_model.py`、`tools/install.py` | `tests/toolkit/test_hierarchy.py`、`tests/system/test_data_hierarchy_system.py` | メタデータ定義と階層・関係索引 |
| FR-1058 | 管理データのメタデータ定義と検査 | 承認済み | `scripts/metadata.json`、`scripts/ebaklib.py`、`scripts/rdcheck.py`、`EABK-Studio/eabk_model.py`、`tools/install.py` | `tests/toolkit/test_hierarchy.py`、`tests/system/test_data_hierarchy_system.py` | メタデータ定義と階層・関係索引 |
| FR-1059 | 関係の索引（種類つきの関連付け） | 承認済み | `scripts/metadata.json`、`scripts/ebaklib.py`、`scripts/rdcheck.py`、`EABK-Studio/eabk_model.py`、`tools/install.py` | `tests/toolkit/test_hierarchy.py`、`tests/system/test_data_hierarchy_system.py` | メタデータ定義と階層・関係索引 |
| FR-1060 | 領域の初期分類（AI提案） | 承認済み | 未実装 | 未実装 | - |
| FR-1078 | 要求・受入基準・System Test のケースの数の最適化（似た既存の項目の再利用と重複の統合） | 承認済み | `scripts/rdcheck.py`、`scripts/ledger.py`、`.github/agents/rd-author.agent.md`、`.github/agents/test-designer.agent.md`、`.github/agents/conductor.agent.md`、`.github/skills/requirement-definition/SKILL.md`、`.github/skills/rd-audit/SKILL.md` | `tests/integration/test_reuse_optimization_it.py` | データ層検査、配布同期対象 |
| FR-1062 | 各データの上位層の定義（種類→区分→領域→項目） | 承認済み | `EABK-Studio/eabk_model.py`、`EABK-Studio/web/js/hier.js`、`scripts/rdcheck.py`、`tools/install.py` | `EABK-Studio/tests/test_tier_hierarchy.py`、`tests/system/test_data_tiers_system.py` | 階層の導出、階層の共通 JS 部品 |
| FR-1063 | Studio の全画面での上位層の表示 | 承認済み | `EABK-Studio/web/js/tierlist.js`、`EABK-Studio/web/js/tables.js`、`EABK-Studio/web/js/integrations.js`、`EABK-Studio/web/js/entities.js`、`EABK-Studio/web/js/implstatus.js`、`EABK-Studio/web/js/dashboard.js`、`EABK-Studio/web/js/diagrams.js`、`EABK-Studio/web/js/source.js`、`EABK-Studio/web/js/insights.js`、`EABK-Studio/web/js/maptiers.js`、`EABK-Studio/web/js/map2d.js`、`EABK-Studio/web/js/map3d.js`、`EABK-Studio/web/js/maprpg.js`、`EABK-Studio/web/app.css`、`EABK-Studio/web/rpg.css` | `EABK-Studio/tests/test_tier_lists_ui.py`、`tests/system/e2e/test_studio_tiers_system.py`、`EABK-Studio/tests/test_map_tiers_ui.py`、`EABK-Studio/tests/test_tier_reflow_a11y_ui.py` | 階層の共通 JS 部品、一覧の階層ブリッジ、マップの上位層パネル |
| NFR-UX-014 | 管理データの情報デザイン（段階的開示と一覧性） | 承認済み | `scripts/metadata.json`、`scripts/ebaklib.py`、`scripts/rdcheck.py`、`EABK-Studio/eabk_model.py`、`tools/install.py` | `tests/toolkit/test_hierarchy.py`、`tests/system/test_data_hierarchy_system.py` | メタデータ定義と階層・関係索引 |
| FR-1050 | 表・連携の ID の全面リンク化と未解決 ID の明示 | 承認済み | 未実装 | tests/system/e2e/test_studio_info_design_system.py | - |
| FR-1051 | 「表」画面の種別のグループ化と名称の統一 | 承認済み | 未実装 | tests/system/e2e/test_studio_info_design_system.py | - |
| FR-1052 | 文脈の明示と、図・一覧の行のキーボード操作 | 承認済み | 未実装 | tests/system/e2e/test_studio_info_design_system.py | - |
| FR-1064 | 監視コマンド watch.py（scan・reap・stuck） | 承認済み | `scripts/watch.py` | `tests/toolkit/test_watch.py`、`tests/integration/test_watch_cli.py` | run 監視 |
| FR-1065 | run の運用への組込み（統合時の回収・状態の警告・手順書の規則） | 承認済み | `scripts/integrate.py`、`scripts/run-state.py`、`tools/install.py`、`.github/agents/conductor.agent.md`、`.github/skills/implement-fr/SKILL.md`、`users-guide/05-scripts-reference.md` | `tests/toolkit/test_integrate_reap.py`、`tests/system/test_watch_status_system.py`、`tests/toolkit/test_watch_docs.py` | run 監視、worktree pool 管理、run 状態・完了記録 |
| NFR-OPS-008 | 監視コマンドの安全性・配布・文書・単体テスト | 承認済み | `scripts/watch.py`、`tools/install.py`、`users-guide/05-scripts-reference.md` | `tests/toolkit/test_watch.py`、`tests/toolkit/test_watch_docs.py` | run 監視 |
| FR-1074 | start-claim と start の排他・結びつけ（持ち主の取り違え防止） | 承認済み（包括承認 2026-10-22・approval_policy） | scripts/run-state.py, scripts/ebaklib.py | `tests/toolkit/test_start_claim.py`、`tests/toolkit/test_parallel_hook.py` | run 状態・完了記録 |
| FR-1075 | 所有者なし run の救済の厳格化 | 承認済み（包括承認 2026-10-22・approval_policy） | scripts/hooks/gate.py | `tests/toolkit/test_multi_run.py`、`tests/toolkit/test_start_claim.py`、`tests/integration/test_hook_rescue_template_it.py` | hook ゲート |
| FR-1076 | 主ツリーで run を置いたときの別 session のゲート対象外 | 承認済み（包括承認 2026-10-22・approval_policy） | users-guide/06-quality-gates.md | `tests/toolkit/test_parallel_hook.py` | hook ゲート |
| FR-1077 | /build template 状態の session ごとの分離 | 承認済み（包括承認 2026-10-22・approval_policy） | scripts/hooks/gate.py | `tests/toolkit/test_parallel_hook.py`、`tests/integration/test_hook_rescue_template_it.py` | hook ゲート |
| NFR-OPS-009 | 並列開始の統合試験 | 承認済み（包括承認 2026-10-22・approval_policy） | `scripts/hooks/gate.py`、`scripts/run-state.py` | `tests/integration/test_parallel_start_it.py`、`tests/toolkit/test_parallel_hook.py` | hook ゲート、run 状態・完了記録 |
| NFR-OPS-010 | 排他の安全性・配布・文書 | 承認済み（包括承認 2026-10-22・approval_policy） | users-guide/07-troubleshooting.md | `tests/toolkit/test_parallel_hook.py`、`tests/toolkit/test_start_claim.py`、`tests/toolkit/test_install.py` | 配布同期対象 |
| FR-1066 | ヘッダー常設の表示モード切替（2D・3D・RPG 風・Graph） | 承認済み | `EABK-Studio/web/js/dim.js`、`EABK-Studio/web/js/app.js`、`EABK-Studio/web/js/diagrams.js`、`EABK-Studio/web/js/entities.js`、`EABK-Studio/web/js/i18n.js`、`EABK-Studio/web/index.html`、`EABK-Studio/web/app.css` | `EABK-Studio/tests/test_header_dim_ui.py`、`tests/system/e2e/test_studio_header_dim_3d_part1_system.py` | 2D・3D 切替、意味的ズーム |
| FR-1067 | 表示モード切替をまたぐ意味的ズームの引継ぎ | 承認済み | `EABK-Studio/web/js/entities.js`、`EABK-Studio/web/js/semzoom.js`、`EABK-Studio/web/js/dim.js` | `EABK-Studio/tests/test_header_dim_ui.py`、`tests/system/e2e/test_studio_header_dim_3d_part1_system.py` | 2D・3D 切替、意味的ズーム |
| FR-1068 | 3D の種別ごとのオブジェクトと凡例 | 承認済み | `EABK-Studio/web/js/shapes3d.js`、`EABK-Studio/web/js/map3d.js`、`EABK-Studio/web/js/dgm3d.js`、`EABK-Studio/web/js/i18n.js`、`EABK-Studio/web/app.css` | `EABK-Studio/tests/test_obj3d_ui.py`、`EABK-Studio/tests/test_dgm3d_shapes.py`、`tests/system/e2e/test_studio_header_dim_3d_part1_system.py` | 3D 種別かたち・演出スタイル、Three.js 同梱モジュール、デザイン基盤 |
| FR-1069 | 3D 演出スタイル（Software Engineering／Entertainment）の切替 | 承認済み | `EABK-Studio/web/js/shapes3d.js`、`EABK-Studio/web/js/map3d.js`、`EABK-Studio/web/js/dgm3d.js`、`EABK-Studio/web/js/i18n.js`、`EABK-Studio/web/app.css` | `EABK-Studio/tests/test_obj3d_ui.py`、`EABK-Studio/tests/test_dgm3d_shapes.py`、`tests/system/e2e/test_studio_header_dim_3d_part1_system.py` | 3D 種別かたち・演出スタイル、Three.js 同梱モジュール、デザイン基盤 |
| FR-1070 | 3D カメラのプリセット（平易な名称・説明と 4 要素の記述） | 承認済み | `EABK-Studio/web/js/camera3d.js`、`EABK-Studio/web/js/map3d.js`、`EABK-Studio/web/js/dgm3d.js`、`EABK-Studio/web/js/sz3d.js`、`EABK-Studio/web/js/app.js`、`EABK-Studio/web/js/i18n.js`、`EABK-Studio/web/app.css` | `EABK-Studio/tests/test_camera3d_ui.py`、`EABK-Studio/tests/test_dgm3d_shapes.py`、`tests/system/e2e/test_studio_camera_presets_system.py` | 3D カメラのプリセット、デザイン基盤 |
| FR-1071 | カメラ動作の動きの軽減と手動操作の優先 | 承認済み | `EABK-Studio/web/js/camera3d.js`、`EABK-Studio/web/js/map3d.js`、`EABK-Studio/web/js/dgm3d.js`、`EABK-Studio/web/js/sz3d.js` | `EABK-Studio/tests/test_camera3d_ui.py`、`EABK-Studio/tests/test_dgm3d_shapes.py`、`tests/system/e2e/test_studio_camera_presets_system.py` | 3D カメラのプリセット |
| NFR-UX-015 | 3D の種別オブジェクト・演出・カメラの性能と外部通信なし | 承認済み | `EABK-Studio/web/js/camera3d.js`、`EABK-Studio/web/js/map3d.js`、`EABK-Studio/web/js/i18n.js` | `EABK-Studio/tests/test_camera3d_ui.py`、`tests/system/e2e/test_studio_camera_presets_system.py` | 3D カメラのプリセット、Three.js 同梱モジュール |
| FR-1072 | ヘッダー・ナビの複数段への自動折り返し配置 | 承認済み | `EABK-Studio/web/app.css`、`EABK-Studio/web/index.html` | `EABK-Studio/tests/test_header_row_ui.py`、`tests/system/e2e/test_studio_header_row_system.py` | デザイン基盤 |
| NFR-UX-016 | 常設要素が重ならない | 承認済み | `EABK-Studio/web/app.css`、`EABK-Studio/web/js/maptiers.js`、`EABK-Studio/web/js/map2d.js`、`EABK-Studio/web/js/map3d.js` | `EABK-Studio/tests/test_header_row_ui.py`、`tests/system/e2e/test_studio_header_row_system.py` | デザイン基盤 |
| FR-1079 | Graph 表示モード（関係をノードと辺で見る） | 承認済み | `EABK-Studio/web/js/graph.js`、`EABK-Studio/web/js/mapgraph.js`、`EABK-Studio/web/js/dim.js`、`EABK-Studio/web/js/app.js`、`EABK-Studio/web/js/diagrams.js`、`EABK-Studio/web/js/entities.js`、`EABK-Studio/web/js/ui.js`、`EABK-Studio/web/js/i18n.js`、`EABK-Studio/web/app.css` | `EABK-Studio/tests/test_graph_mode_ui.py`、`tests/system/e2e/test_studio_header_dim_3d_part1_system.py` | Graph 描画部品、2D・3D 切替、UI 部品、デザイン基盤 |
| FR-1080 | Studio の全可視化要素の動的なデータ表現（データ結合・トランジション・ホバー・ズーム・force 風レイアウト） | 承認済み | `EABK-Studio/web/js/viz.js`、`EABK-Studio/web/js/graph.js`、`EABK-Studio/web/js/map2d.js`、`EABK-Studio/web/js/semzoom.js`、`EABK-Studio/web/js/diagrams.js`、`EABK-Studio/web/js/dashboard.js`、`EABK-Studio/web/js/insights.js`、`EABK-Studio/web/js/implstatus.js`、`EABK-Studio/web/js/tables.js`、`EABK-Studio/web/js/ui.js`、`EABK-Studio/web/js/i18n.js`、`EABK-Studio/web/app.css`、`EABK-Studio/web/index.html` | `EABK-Studio/tests/test_dynamic_viz_ui.py`、`EABK-Studio/tests/test_graph_dynamics_ui.py`、`tests/system/e2e/test_studio_dynamic_viz_system.py` | 動的可視化の小部品、Graph 描画部品、UI 部品、デザイン基盤 |
| NFR-UX-018 | 動的な可視化の性能・外部依存なし・安全な更新 | 承認済み | `EABK-Studio/web/js/viz.js` | `EABK-Studio/tests/test_dynamic_viz_ui.py`、`tests/system/e2e/test_studio_dynamic_viz_system.py` | 動的可視化の小部品 |

## API・イベント

| 名前 | 定義ファイル | 関連する要求 ID |
|---|---|---|

## テーブル

| テーブル名 | 定義ファイル | 正本のシステム | 関連する要求 ID |
|---|---|---|---|

## 共通部品

| 部品名 | ファイル | 用途 | 使っている要求 ID |
|---|---|---|---|
| run 作業資産清掃 | `scripts/clean-work.py` | 正常完了・main 統合後ゲート、所有権、保護状態にもとづく計画・清掃・診断・冪等再試行 | FR-1009、FR-1010、NFR-OPS-005、NFR-COMPAT-001 |
| run 監視 | `scripts/watch.py` | 残留プロセスの scan・reap（名前とリポジトリのパスで限定）と queue の doing 時間超過 stuck の検出 | FR-1064、FR-1065、NFR-OPS-008 |
| run 状態・完了記録 | `scripts/run-state.py` | run の完了条件、finish、run-history と current-run の状態管理（start-claim の消費と持ち主の記録を含む） | FR-1010、FR-1015、FR-1016、FR-1065、FR-1074、NFR-COMPAT-001、NFR-OPS-005、NFR-OPS-009 |
| hook ゲート | `scripts/hooks/gate.py` | hook の G-1・G-5 などのゲート、start-claim の記録、所有者なし run の救済、template 状態の保存 | FR-1075、FR-1076、FR-1077、NFR-OPS-009 |
| 3D カメラのプリセット | `EABK-Studio/web/js/camera3d.js` | 9 種のプリセット表 `CAMERA_PRESETS`（落ち着き→派手。Shot Size×Camera Angle×Camera Movement×Motion Character の 4 要素・語彙・別名表。1 か所）、操作部品 `createCameraRig`（`camera-presets`・`camera-detail`・`data-camera-auto`・`data-reduced-motion`・`window.__eabk3d.camera()`）、動きの軽減で Static、手動操作・Esc・停止ボタンで自動動作を止める、性能不足（PARAM-047 未満）で Static へ縮退（保存値は書かない）、コマンド検索の `cameraCommands()`。WebGL 版（map3d.js）と Canvas 版（sz3d.js）が共用 | FR-1070、FR-1071、NFR-UX-015 |
| 3D 種別かたち・演出スタイル | `EABK-Studio/web/js/shapes3d.js` | 3D のノード種別 → かたち（three.js 標準ジオメトリの組合せ）の対応表 `SHAPE_OF`（1 か所。凡例・3D の描画・テストが参照）、InstancedMesh による描画、凡例（`legend-3d`）、演出スタイルの切替（`style-toggle`。保存は localStorage `eabk-studio.style3d` にスタイル名のみ）。未知の種別は `default`（その他） | FR-1068、FR-1069 |
| worktree pool 管理 | `scripts/integrate.py` | pool worktree の列挙、強制削除、Git worktree 登録の prune | FR-1009、FR-1065、NFR-OPS-005、NFR-COMPAT-001 |
| conductor 終了契約 | [`.github/agents/conductor.agent.md`](docs/../.github/agents/conductor.agent.md) | run 開始時・工程 6・main 統合・run-report・清掃の実行順序 | FR-1009、FR-1010、NFR-COMPAT-001 |
| run 運用ガイド | `users-guide/02-during-and-after-run.md`、`users-guide/05-scripts-reference.md`、`users-guide/07-troubleshooting.md` | 利用者向けの統合、清掃、診断、再開、トラブルシューティング契約 | FR-1010、NFR-COMPAT-001 |
| 配布同期対象 | `tools/install.py` | conductor、清掃・状態・統合スクリプトをインストール対象へ同期する管理対象。外部連携カタログの雛形（TEMPLATES。なければ作成）と検査・チェックリスト（MANAGED）も配る | FR-1015、FR-1016、FR-1017、FR-1037、FR-1038、FR-1039、FR-1045、FR-1078、NFR-COMPAT-001、NFR-OPS-006、NFR-OPS-007、NFR-OPS-010、NFR-SEC-004 |
| git ls-files 並行取得 | `scripts/ebaklib.py` | `tracked_files` で tracked・untracked 一覧を ThreadPoolExecutor で並行取得し、rdcheck/rdfix は同一引数の呼び出しを 1 回にする | NFR-PERF-003、NFR-COMPAT-002 |
| System Test の選択 | `scripts/ledger.py` | `select_cases` が `--select changed` で git diff の追加・変更行の要求 ID・AC ID を優先してケースを選び、ケースごとに理由を出力する。共通コード・解析不能・ID なしは広げる（従来の選択を含む） | NFR-PERF-003 |
| 次実装候補の分析 | `scripts/next-impl.py` | 承認済み・未完了の要求を優先度・依存・実装状態で順位付けし、除外の理由と scope 用 ID 一覧を出す（読み取り専用） | FR-1015、FR-1016 |
| 外部連携カタログ解析・検査 | `scripts/ebaklib.py`、`scripts/rdcheck.py`、`scripts/next-id.py` | `docs/integrations.md` の解析（`parse_integrations`）、CHK-28 の検査（必須欄・16 観点の欄・値の形式・TBD・方向・状態・要求との対応・認証情報の値らしい文字列）、`trace INT-xxx`、`next-id.py INT` の採番と ID 台帳の同期 | FR-1035、FR-1036、FR-1037 |
| データ層検査 | `scripts/verify.py` | `--docs-only` でデータ層の妥当性を検査する | FR-1017、FR-1018、FR-1044、FR-1046、FR-1078、NFR-PERF-005 |
| データ層修復 | `scripts/rdfix.py` | 要求定義書を変更せずデータ層の不整合を自動修復し、残りを手動対応として示す | FR-1018、FR-1019、FR-1044、FR-1045、FR-1046、NFR-COMPAT-004、NFR-PERF-005、NFR-REL-002、NFR-REL-003、NFR-REL-004 |
| メタデータ定義と階層・関係索引 | `scripts/metadata.json`、`scripts/ebaklib.py`、`scripts/rdcheck.py` | 欄名・必須/任意・許容値の定義（metadata.json）、領域の欄・一覧表・割り当て表の検査（CHK-29/30）、列名の一致（CHK-31）、節の項目数の警告（CHK-32）、`rdcheck.py list --area/--by-area`、種類つきの関係の索引（`rdcheck.py index`。保存せず都度生成） | FR-1057、FR-1058、FR-1059、NFR-UX-014 |
| 階層の導出 | `EABK-Studio/eabk_model.py`、`scripts/rdcheck.py` | 種類→区分→領域→項目の階層を `derive_hierarchy` で 1 か所から導出する（要求の区分は ID 接頭辞、領域は各要求の領域の欄、領域のないデータは既存の節・分類、定まらないものだけ「未分類」。割り当て表は持たず都度生成）。`/api/model` の `model.hierarchy`、`rdcheck.py hierarchy [--json]` | FR-1062 |
| 階層の共通 JS 部品 | `EABK-Studio/web/js/hier.js` | 全画面で使う階層の描画（見出し・件数・開閉・未分類・JA/EN の名称・キーボード操作・aria 属性・記号で示す開閉）。`renderTiers` / `buildTree` / `tierName`。0 件でも見出しを出す `hier.empty` を持つ | FR-1062、FR-1063 |
| 一覧の階層ブリッジ | `EABK-Studio/web/js/tierlist.js` | 一覧・表・実装状態・ダッシュボード・図式・ソース・保守の各画面が、行・項目を `model.hierarchy` の (種類, ID) に対応づけて hier.js で描く（`placeRows` / `listTiers`）。階層にない行は明示の「未分類」。開閉状態は一覧系の画面で共有 | FR-1063 |
| マップの上位層パネル | `EABK-Studio/web/js/maptiers.js` | 2D・3D のマップ本体で点を上位層（種類→区分→領域）ごとの帯・円盤にまとめ、見出しに名称・件数・▾/▸を出し、ダブルクリック（キーボードはパネルの木）で畳むと件数つきの塊に集約する。隅のパネルと RPG 風の会話ウィンドウは階層の共通 JS 部品で同じ上位層を出し、開閉状態を画面間で共有する（tierState）。RPG 風は街・住人・城の会話に関連する要求の上位層の件数と「上位層で辿る」、スタートメニュー「項目の上位層」（城・街・住人の件数には加えない） | FR-1063 |
| エンティティ台帳・企業カタログ照合 | `scripts/entities.py` | 用語表・状態表・対象エンティティ・カタログのテーブル表からエンティティ台帳を導出し（list）、企業データカタログ（任意設定 `enterprise_data_catalog`。読み取り専用）と照合し（check）、覆われないものを質問票形式の ToDo にする（todo）。導出関数 `derive` は Studio からも再利用する。任意欄: 要求の `エンティティの関係`、カタログの `### 列: <テーブル>` 節の表、DDL・JSON Schema の読み取り専用の補完（列・関係・クラスターも導出する） | FR-1020、FR-1021、FR-1022、FR-1023、FR-1024、FR-1025、FR-1026、FR-1030、NFR-COMPAT-003、NFR-SEC-023 |
# EABK Studio カタログ

管理データの要求と、現時点で実在する実装資産の対応表。未実装の要求は「未実装」と記載する。`EABK-Studio` は依頼時点の作業ツリーに存在する資産であり、今回の要求定義コミットではコードを変更しない。

## 機能

| 要求 ID | 題名 | 決定状態 | 実装ファイル | テスト | 使っている共通部品 |
|---|---|---|---|---|---|
| FR-001 | 管理データのモデル化 | 承認済み（依頼 2026-10-09） | `EABK-Studio/eabk_model.py` | `EABK-Studio/tests/test_studio.py` | 管理データモデル |
| FR-002 | ダッシュボードと進捗 | 承認済み（依頼 2026-10-09） | `EABK-Studio/web/js/dashboard.js` | `tests/system/e2e/test_studio_system.py` | ストア、デザイン基盤 |
| FR-003 | 2D/3D 関係マップ | 承認済み（依頼 2026-10-09） | `EABK-Studio/web/js/map2d.js`, `EABK-Studio/web/js/map3d.js` | `tests/system/e2e/test_studio_system.py` | ストア、Three.js 同梱モジュール、デザイン基盤 |
| FR-004 | 図式化 | 承認済み（包括承認 2026-10-12・approval_policy） | `EABK-Studio/web/js/diagrams.js`, `EABK-Studio/web/js/i18n.js` | `tests/system/e2e/test_studio_system.py`, `EABK-Studio/tests/test_studio.py` | ストア、デザイン基盤 |
| FR-005 | 配置と表現の切替 | 承認済み（依頼 2026-10-09） | `EABK-Studio/web/js/placement.js` | `tests/system/e2e/test_studio_system.py` | ストア、デザイン基盤 |
| FR-006 | 表と検索 | 承認済み（依頼 2026-10-09） | `EABK-Studio/web/js/tables.js` | `tests/system/e2e/test_studio_system.py` | UI 部品、ストア、デザイン基盤 |
| FR-007 | ソース対応 | 承認済み（依頼 2026-10-09） | `EABK-Studio/web/js/source.js` | `tests/system/e2e/test_studio_system.py` | ストア |
| FR-008 | ペルソナ既定表現 | 承認済み（依頼 2026-10-09） | `EABK-Studio/web/js/app.js`, `EABK-Studio/web/js/dashboard.js` | `tests/system/e2e/test_studio_system.py` | ストア、デザイン基盤 |
| FR-009 | 履歴・理想状態・整合性 | 承認済み（依頼 2026-10-09） | `EABK-Studio/eabk_model.py`, `EABK-Studio/web/js/dashboard.js` | `EABK-Studio/tests/test_studio.py`, `tests/system/e2e/test_studio_system.py` | 管理データモデル |
| FR-010 | リポジトリの既定と切替 | 承認済み（依頼 2026-10-09） | `EABK-Studio/studio.py`, `EABK-Studio/web/js/app.js`, `EABK-Studio/web/js/ui.js`, `EABK-Studio/web/js/i18n.js`, `EABK-Studio/web/index.html` | `EABK-Studio/tests/test_studio.py`, `EABK-Studio/tests/test_repo_switch_recovery_wiring.py`, `tests/system/e2e/test_studio_repo_pick_system.py` | HTTP サーバー |
| FR-011 | JA/EN とリンク | 承認済み（依頼 2026-10-09） | `EABK-Studio/web/js/i18n.js`、`EABK-Studio/web/js/app.js`、`EABK-Studio/web/index.html`、`EABK-Studio/web/js/insights.js`、`EABK-Studio/web/js/hier.js`、`EABK-Studio/web/js/maprpg.js`、`EABK-Studio/web/js/maptiers.js` | `tests/system/e2e/test_studio_system.py`、`tests/system/e2e/test_studio_lang_toggle_system.py`、`EABK-Studio/tests/test_i18n_coverage.py`、`EABK-Studio/tests/i18n_scan.py` | 言語辞書、UI 部品、デザイン基盤 |
| FR-012 | 鮮度検知と再読込 | 承認済み（依頼 2026-10-09） | `EABK-Studio/studio.py` | `EABK-Studio/tests/test_studio.py` | フィンガープリント |
| FR-013 | 通常操作の参照専用データ境界 | 廃止 | 未実装 | 未実装 | なし |
| FR-1001 | users-guide の利用開始前提条件 | 承認済み（依頼 2026-10-09） | 未実装 | AC-037 対応の E2E-015 は登録・実装済み、commit `c61ee5b` の実行結果は `fail`（合格ではない） | 起動スクリプト、HTTP サーバー |
| NFR-UX-001 | レイアウト変更 | AI提案／承認待ち | 未実装 | 未実装 | なし |
| NFR-UX-002 | レイアウト復元 | 承認済み | `EABK-Studio/web/js/layout.js`、`EABK-Studio/web/js/app.js`、`EABK-Studio/web/index.html`、`EABK-Studio/web/app.css`、`EABK-Studio/web/js/i18n.js` | `tests/system/e2e/test_studio_layout_authz_system.py` | 画面の配置 |
| NFR-UX-003 | 非ドラッグ操作 | 承認済み | 未実装 | 未実装 | なし |
| NFR-UX-004 | 狭い画面と拡大 | 承認済み | 未実装 | 未実装 | なし |
| NFR-UX-005 | 一貫した操作結果 | AI提案／承認待ち | `EABK-Studio/web/js/i18n.js` | 未実装 | UI 部品 |
| NFR-UX-006 | 表現の連動 | AI提案／承認待ち | 未実装 | 未実装 | なし |
| NFR-UX-007 | 視覚表現の代替 | 承認済み | `EABK-Studio/web/js/tables.js`, `EABK-Studio/web/js/diagrams.js` | 未実装 | UI 部品 |
| NFR-UX-008 | ペルソナ表現の安全な切替 | 承認済み | 未実装 | 未実装 | なし |
| NFR-UX-009 | 状態と進行表示 | AI提案／承認待ち | 未実装 | 未実装 | なし |
| NFR-SEC-001 | ローカル限定 | 承認済み（依頼 2026-10-09） | `EABK-Studio/studio.py` | `EABK-Studio/tests/test_studio.py` | HTTP サーバー |
| NFR-SEC-002 | 読取安全性 | 承認済み（依頼 2026-10-23） | `EABK-Studio/studio.py` | `EABK-Studio/tests/test_studio.py` | 管理データモデル、HTTP サーバー |
| NFR-SEC-003 | 権限・外部連携境界 | 承認済み | 未実装 | 未実装 | なし |
| NFR-OPS-001 | 実行環境 | 承認済み（依頼 2026-10-09） | `EABK-Studio/studio.py` | `EABK-Studio/tests/test_studio.py` | 起動スクリプト |
| NFR-OPS-002 | 自動再読込の継続 | 承認済み（依頼 2026-10-09） | `EABK-Studio/web/js/app.js` | 未実装 | フィンガープリント |
| NFR-OPS-003 | 不足・失敗からの復旧 | 承認済み（依頼 2026-10-09） | `EABK-Studio/studio.py`, `EABK-Studio/web/js/app.js`, `EABK-Studio/web/js/ui.js` | `EABK-Studio/tests/test_studio.py`, `EABK-Studio/tests/test_repo_switch_recovery_wiring.py` | HTTP サーバー、UI 部品 |
| NFR-OPS-004 | 管理データとの互換性 | 承認済み（依頼 2026-10-09） | `scripts/ebak.config.json`, `EABK-Studio/eabk_model.py` | `EABK-Studio/tests/test_studio.py` | 管理データモデル |
| FR-1002 | 全画面のペルソナ別分析説明 | 承認済み（包括承認 2026-10-09・approval_policy） | `EABK-Studio/web/js/insights.js` | `EABK-Studio/tests/test_studio.py` | ストア、UI 部品、デザイン基盤 |
| FR-1003 | 全データ層の現状対理想と構造妥当性 | 承認済み（包括承認 2026-10-09・approval_policy） | `EABK-Studio/eabk_model.py`, `EABK-Studio/web/js/insights.js` | `EABK-Studio/tests/test_studio.py` | 管理データモデル、ストア、UI 部品、デザイン基盤 |
| FR-1004 | 安全で明示的な整合性保守 | 承認済み（包括承認 2026-10-09・approval_policy） | 未実装 | 未実装 | - |
| FR-1005 | アプリ構成とデータ位置づけ | 承認済み（包括承認 2026-10-09・approval_policy） | `EABK-Studio/eabk_model.py`, `EABK-Studio/web/js/insights.js` | `EABK-Studio/tests/test_studio.py` | 管理データモデル、ストア、UI 部品、デザイン基盤 |
| FR-1006 | 設計・開発判断の統合可視化 | 承認済み（包括承認 2026-10-09・approval_policy） | `EABK-Studio/eabk_model.py`, `EABK-Studio/web/js/insights.js` | `EABK-Studio/tests/test_studio.py` | 管理データモデル、ストア、UI 部品、デザイン基盤 |
| FR-1007 | users-guide 実画面スクリーンショット | 承認済み（包括承認 2026-10-09・approval_policy） | `users-guide/studio/capture-screens.py`, `users-guide/studio/screen-images.json`, `users-guide/studio/images/` | 未実装 | - |

## API・イベント

| 名前 | 定義ファイル | 関連する要求 ID |
|---|---|---|
| `GET /api/model` | `EABK-Studio/studio.py` | FR-001、FR-009 |
| `GET /api/fingerprint` | `EABK-Studio/studio.py` | FR-012、NFR-OPS-002 |
| `GET /api/repo` | `EABK-Studio/studio.py` | FR-010 |
| `POST /api/repo` | `EABK-Studio/studio.py` | FR-010、NFR-OPS-003 |
| `POST /api/repo/pick` | `EABK-Studio/studio.py` | FR-010 |
| 管理データフィンガープリント変化 | `EABK-Studio/web/js/app.js` | FR-012、NFR-OPS-002 |

## テーブル

| テーブル名 | 定義ファイル | 正本のシステム | 関連する要求 ID |
|---|---|---|---|
| 要求・AC・PARAM・質問・用語・状態・ペルソナ・出典 | `docs/requirements-definition.md` | 対象リポジトリの要求定義書 | FR-001、FR-006、FR-009、NFR-OPS-004 |
| 機能・API・テーブル・共通部品 | `docs/catalog.md` | 対象リポジトリのカタログ | FR-001、FR-007、FR-009 |
| System Test 台帳 | `tests/system/ledger.json` | 対象リポジトリの台帳 | FR-001、FR-009、NFR-OPS-002 |
| ID 台帳 | `docs/id-registry.md` | 対象リポジトリの ID 台帳 | FR-001、FR-009、NFR-OPS-004 |
| 実行履歴 | `docs/run-history.md` | 対象リポジトリの実行履歴 | FR-009 |

## 共通部品

| 部品名 | ファイル | 用途 | 使っている要求 ID |
|---|---|---|---|
| 管理データモデル | `EABK-Studio/eabk_model.py` | 正本ファイルを読み、ノードと関係を構築 | FR-001、FR-009、FR-1003、FR-1005、FR-1006、FR-1013、FR-1014、FR-1021、FR-1022、FR-1025、FR-1026、FR-1027、FR-1028、FR-1029、FR-1034、FR-1042、FR-1061、NFR-COMPAT-003、NFR-OPS-004、NFR-SEC-002 |
| HTTP サーバー | `EABK-Studio/studio.py` | 127.0.0.1 限定の読取 API と静的配信 | FR-010、FR-1001、NFR-OPS-003、NFR-SEC-001、NFR-SEC-002 |
| ストア | `EABK-Studio/web/js/store.js` | モデル、選択、関連、表現間の状態を共有 | FR-002、FR-003、FR-004、FR-005、FR-006、FR-007、FR-008、FR-1002、FR-1003、FR-1005、FR-1006、FR-1011、FR-1012、FR-1013、FR-1014、FR-1021、FR-1022、FR-1027、FR-1029、FR-1031、FR-1033、FR-1034、FR-1040、FR-1041、FR-1042、FR-1061 |
| UI 部品 | `EABK-Studio/web/js/ui.js`, `EABK-Studio/web/js/xref.js` | 表示、詳細、通知、リンク、状態表示の共通の形 `statePanel`（読込中・空・エラー・古い。`data-testid=state-panel`）、同梱のアイコン 1 セット `icon()`（16・20・24px）、系列色のトークン読み出し `token()` / `TYPE_COLOR` / `STATUS_COLOR` / `IMPL_COLOR` | FR-006、FR-011、FR-1002、FR-1003、FR-1005、FR-1006、FR-1012、FR-1013、FR-1014、FR-1021、FR-1022、FR-1027、FR-1028、FR-1031、FR-1033、FR-1040、FR-1041、FR-1042、FR-1047、FR-1048、FR-1061、FR-1079、FR-1080、NFR-A11Y-001、NFR-OPS-003、NFR-PERF-006、NFR-UX-005、NFR-UX-007、NFR-UX-010 |
| 言語辞書 | `EABK-Studio/web/js/i18n.js` | JA/EN の辞書（`t()`・`data-i18n`・`data-i18n-title`・`data-i18n-ph`・`data-i18n-aria`）と言語の切替 `setLang()`・通知 `onLang()`。選択は言語コード（`ja`／`en` のみ）を localStorage `eabk-studio.lang` に保存・起動時に復元し、`<html lang>`・文書タイトル・ヘッダーの言語トグル `#lang`（JA／EN の button、`aria-pressed`）を更新する。画面の文言の直書きは持たない（管理データの値は訳さない。静的検査は `EABK-Studio/tests/test_i18n_coverage.py`） | FR-011 |
| デザイン基盤 | `EABK-Studio/web/tokens.css`, `EABK-Studio/web/app.css`, `EABK-Studio/web/sz.css`, `EABK-Studio/web/js/theme.js`, `EABK-Studio/web/index.html` | Fluent 2 に寄せた名前付きトークン（`--color-*`・`--font-size-*`・`--space-*`・`--radius-*`・`--shadow-*`・`--stroke-*`・`--duration-*`・`--ease-*`、部品の種類ごとの段階 `--radius-control`・`--radius-container`・`--radius-overlay`・`--radius-tooltip`・`--elevation-*`、素材 `--material-*`、系列色 `--viz-*`、3D 素材色 `--scene-*`。tokens.css の 1 か所）、ライト/ダーク/システムのテーマ（`data-theme`・`data-theme-choice`、テーマ名のみ localStorage `eabk-studio.theme` に保存・起動時に復元、不正値は system）、強制色・動きの軽減・フォーカス表示、外枠、ナビゲーション、検索、通知 | FR-002、FR-003、FR-004、FR-005、FR-006、FR-008、FR-011、FR-1002、FR-1003、FR-1005、FR-1006、FR-1012、FR-1013、FR-1014、FR-1021、FR-1022、FR-1032、FR-1040、FR-1041、FR-1042、FR-1047、FR-1048、FR-1068、FR-1069、FR-1070、FR-1072、FR-1079、FR-1080、NFR-A11Y-001、NFR-PERF-006、NFR-UX-016 |
| RPG 風マップ | `EABK-Studio/web/js/maprpg.js`, `EABK-Studio/web/js/rpgworld.js`, `EABK-Studio/web/js/rpgaudio.js`, `EABK-Studio/web/rpg.css` | 城（目的）と街（エンティティを関係の連結成分でまとめたもの。関係のないものは「関係なしの街」1 つ）を歩いて訪ね、街の住人（エンティティ 1 件）と会話ウィンドウで話して内容を読む 8 ビット風の 2 次元地図。ドット絵と音楽・効果音は Canvas と Web Audio で実行時に生成（外部アセット・外部通信なし、初期ミュート）。ファミコン風のキー操作、表の代替表現、動きの軽減、描画不可なら 2D へ代替 | FR-1053、FR-1054、FR-1055、NFR-UX-012 |
| 2D・3D 切替 | `EABK-Studio/web/js/dim.js`, `EABK-Studio/web/js/dgm3d.js` | マップと図式の 2D・3D 切替アイコン（アニメ調の顔つきの平面・立体と「2D」「3D」の語。外部取得なし）、マップの第 3 の表示「RPG」（城の絵のアイコン）、コマンド検索からの切替、図式の 3D 描画（3D 不可なら 2D と表へ代替） | FR-1040、FR-1041、FR-1053、FR-1054、FR-1055、FR-1066、FR-1067、FR-1079 |
| 動的可視化の小部品 | `EABK-Studio/web/js/viz.js` | d3 非同梱の自前部品。キー付きデータ結合 enter/update/exit（DOM 要素を再利用、消える要素は exit 後に除去）、Web Animations による補間トランジション（PARAM-058 以内。`data-viz-transition` running/settled）、`data-viz`・`data-viz-state`・`data-viz-count`、ホバー・フォーカスの強調 `data-hover`・減光 `data-dim`・`role=tooltip`（Esc で消える）、動きの軽減で `data-reduced-motion=true` と即時切替、連続更新時は進行中の動きを確定して最新へ（重複・取り残しなし）、ホイールのズーム・ドラッグのパン `zoomPan`（`data-zoom`・`data-pan`） | FR-1080、NFR-UX-018 |
| Graph 描画部品 | `EABK-Studio/web/js/graph.js`, `EABK-Studio/web/js/mapgraph.js` | 関係データをノードと向きのある辺（矢印）で描く SVG 部品（外部依存なし）。層レイアウト（左から右）と力学レイアウト（固定回数で決定的）、種類ごとの同梱アイコンと語の併記、キーボード・選択（詳細ドロワー）、150 ノード超の近傍・種類による絞り込みと理由・全体件数の表示。マップの追跡グラフ（mapgraph ルート） | FR-1079、FR-1080 |
| フィンガープリント | `EABK-Studio/studio.py` | 更新検知と再読込 | FR-012、NFR-OPS-002 |
| 画面の配置 | `EABK-Studio/web/js/layout.js` | 配置（default / compact / wide）の変更・既定へ戻す。localStorage `eabk-studio.layout` に配置 ID だけを保存し、不正値は既定。`window.eabkView`（画面共通アクセサ）の `getState().layout = {id, isDefault}` を常に返す | NFR-UX-002 |
| 起動スクリプト | `EABK-Studio/start.ps1`, `EABK-Studio/start.sh` | Windows/macOS/Linux の起動補助 | FR-1001、NFR-OPS-001 |
| 意味的ズーム | `EABK-Studio/web/js/semzoom.js`, `EABK-Studio/web/js/sz2d.js`, `EABK-Studio/web/js/sz3d.js`, `EABK-Studio/web/sz.css` | エンティティの倍率に応じた 3 粒度（クラスター・エンティティと関係線・列の一覧）。2D（SVG）と 3D（Canvas）が 1 つの共有状態（倍率・中心・選択・絞り込み）で動き、可視範囲だけを描画し、表の代替表現・キーボード・JA/EN を備える。`window.eabkView`（setScale・getState）を公開する | FR-1027、FR-1028、FR-1029、FR-1034、FR-1053、FR-1054、FR-1055、FR-1066、FR-1067、NFR-PERF-004、NFR-UX-010 |
| Three.js 同梱モジュール | `EABK-Studio/web/vendor/three.module.min.js` | 3D マップ・3D 図式の表示 | FR-003、FR-1040、FR-1068、FR-1069、NFR-UX-015 |

## 配置先

実在する配置だけを書く（書式は `EABK-Studio/eabk_model.py` の `parse_placements`、FR-1034）。

- 配置先: PC内のフォルダ / 場所: docs/ / アプリ: EABK toolkit のスクリプト、EABK Studio サーバー / データ: 要求定義書、カタログ、ID 台帳、実行履歴、手動テスト手順
- 配置先: PC内のフォルダ / 場所: work/ / アプリ: EABK toolkit のスクリプト / データ: 実行ごとの作業記録（work/runs/）、ログ（work/logs/）
- 配置先: PC内のフォルダ / 場所: tests/system/ / アプリ: EABK toolkit のスクリプト / データ: System Test 台帳（ledger.json）
- 配置先: ブラウザ Local Storage / キー: eabk-studio.lang / アプリ: EABK Studio 画面 / データ: 表示言語（ja か en）
- 配置先: ローカル HTTP サーバー / 待受: 127.0.0.1 / アプリ: EABK Studio サーバー
- 通信: EABK Studio 画面 → EABK Studio サーバー（双方向）
- 通信: EABK Studio サーバー → docs/（受信）
- 通信: EABK Studio サーバー → tests/system/（受信）


