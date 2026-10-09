# EABK Studio カタログ

管理データの要求と、現時点で実在する実装資産の対応表。未実装の要求は「未実装」と記載する。`EABK-Studio` は依頼時点の作業ツリーに存在する資産であり、今回の要求定義コミットではコードを変更しない。

## 機能

| 要求 ID | 題名 | 決定状態 | 実装ファイル | テスト | 使っている共通部品 |
|---|---|---|---|---|---|
| FR-001 | 管理データのモデル化 | 承認済み（依頼 2026-10-09） | `EABK-Studio/eabk_model.py` | `EABK-Studio/tests/test_studio.py` | 管理データモデル |
| FR-002 | ダッシュボードと進捗 | 承認済み（依頼 2026-10-09） | `EABK-Studio/web/js/dashboard.js` | 未実装 | ストア |
| FR-003 | 2D/3D 関係マップ | 承認済み（依頼 2026-10-09） | `EABK-Studio/web/js/map2d.js`, `EABK-Studio/web/js/map3d.js` | 未実装 | ストア、Three.js 同梱モジュールモジュール |
| FR-004 | 図式化 | 承認済み（依頼 2026-10-09） | `EABK-Studio/web/js/diagrams.js` | 未実装 | ストア |
| FR-005 | 配置と表現の切替 | 承認済み（依頼 2026-10-09） | `EABK-Studio/web/js/placement.js` | 未実装 | ストア |
| FR-006 | 表と検索 | 承認済み（依頼 2026-10-09） | `EABK-Studio/web/js/tables.js` | 未実装 | UI 部品、ストア |
| FR-007 | ソース対応 | 承認済み（依頼 2026-10-09） | `EABK-Studio/web/js/source.js` | 未実装 | ストア |
| FR-008 | ペルソナ既定表現 | 承認済み（依頼 2026-10-09） | `EABK-Studio/web/js/dashboard.js` | 未実装 | ストア |
| FR-009 | 履歴・理想状態・整合性 | 承認済み（依頼 2026-10-09） | `EABK-Studio/eabk_model.py` | 未実装 | 管理データモデル |
| FR-010 | リポジトリの既定と切替 | 承認済み（依頼 2026-10-09） | `EABK-Studio/studio.py` | `EABK-Studio/tests/test_studio.py` | HTTP サーバー |
| FR-011 | JA/EN とリンク | 承認済み（依頼 2026-10-09） | `EABK-Studio/web/js/i18n.js` | 未実装 | UI 部品 |
| FR-012 | 鮮度検知と再読込 | 承認済み（依頼 2026-10-09） | `EABK-Studio/studio.py` | `EABK-Studio/tests/test_studio.py` | フィンガープリント |
| FR-013 | 参照専用データ境界 | 承認済み（依頼 2026-10-09） | `EABK-Studio/studio.py` | `EABK-Studio/tests/test_studio.py` | HTTP サーバー |
| FR-1000 | 利用前提条件の案内 | 承認済み（依頼 2026-10-09） | 未実装 | 未実装（AC-036 は manual） | なし |
| NFR-UX-001 | レイアウト変更 | AI提案／承認待ち | 未実装 | 未実装 | なし |
| NFR-UX-002 | レイアウト復元 | AI提案／承認待ち | 未実装 | 未実装 | なし |
| NFR-UX-003 | 非ドラッグ操作 | AI提案／承認待ち | 未実装 | 未実装 | なし |
| NFR-UX-004 | 狭い画面と拡大 | AI提案／承認待ち | 未実装 | 未実装 | なし |
| NFR-UX-005 | 一貫した操作結果 | AI提案／承認待ち | `EABK-Studio/web/js/i18n.js` | 未実装 | UI 部品 |
| NFR-UX-006 | 表現の連動 | AI提案／承認待ち | 未実装 | 未実装 | なし |
| NFR-UX-007 | 視覚表現の代替 | AI提案／承認待ち | `EABK-Studio/web/js/tables.js`, `EABK-Studio/web/js/diagrams.js` | 未実装 | UI 部品 |
| NFR-UX-008 | ペルソナ表現の安全な切替 | AI提案／承認待ち | 未実装 | 未実装 | なし |
| NFR-UX-009 | 状態と進行表示 | AI提案／承認待ち | 未実装 | 未実装 | なし |
| NFR-SEC-001 | ローカル限定 | 承認済み（依頼 2026-10-09） | `EABK-Studio/studio.py` | `EABK-Studio/tests/test_studio.py` | HTTP サーバー |
| NFR-SEC-002 | 読取安全性 | 承認済み（依頼 2026-10-09） | `EABK-Studio/studio.py` | `EABK-Studio/tests/test_studio.py` | 管理データモデル |
| NFR-SEC-003 | 権限・外部連携境界 | AI提案／承認待ち | 未実装 | 未実装 | なし |
| NFR-OPS-001 | 実行環境 | 承認済み（依頼 2026-10-09） | `EABK-Studio/studio.py` | `EABK-Studio/tests/test_studio.py` | 起動スクリプト |
| NFR-OPS-002 | 自動再読込の継続 | 承認済み（依頼 2026-10-09） | `EABK-Studio/web/js/app.js` | 未実装 | フィンガープリント |
| NFR-OPS-003 | 不足・失敗からの復旧 | 承認済み（依頼 2026-10-09） | `EABK-Studio/studio.py` | `EABK-Studio/tests/test_studio.py` | HTTP サーバー、UI 部品 |
| NFR-OPS-004 | 管理データとの互換性 | 承認済み（依頼 2026-10-09） | `scripts/ebak.config.json`, `EABK-Studio/eabk_model.py` | `EABK-Studio/tests/test_studio.py` | 管理データモデル |

## API・イベント

| 名前 | 定義ファイル | 関連する要求 ID |
|---|---|---|
| `GET /api/model` | `EABK-Studio/studio.py` | FR-001、FR-009 |
| `GET /api/fingerprint` | `EABK-Studio/studio.py` | FR-012、NFR-OPS-002 |
| `GET /api/repo` | `EABK-Studio/studio.py` | FR-010 |
| `POST /api/repo` | `EABK-Studio/studio.py` | FR-010、NFR-OPS-003 |
| 管理データフィンガープリント変化 | `EABK-Studio/web/js/app.js` | FR-012、NFR-OPS-002 |

## テーブル

| テーブル名 | 定義ファイル（スキーマやマイグレーション） | 正本のシステム | 関連する要求 ID |
|---|---|---|---|
| 要求・AC・PARAM・質問・用語・状態・ペルソナ・出典 | `docs/requirements-definition.md` | 対象リポジトリの要求定義書 | FR-001、FR-006、FR-009、NFR-OPS-004 |
| 機能・API・テーブル・共通部品 | `docs/catalog.md` | 対象リポジトリのカタログ | FR-001、FR-007、FR-009 |
| System Test 台帳 | `tests/system/ledger.json` | 対象リポジトリの台帳 | FR-001、FR-009、NFR-OPS-002 |
| ID 台帳 | `docs/id-registry.md` | 対象リポジトリの ID 台帳 | FR-001、FR-009、NFR-OPS-004 |
| 実行履歴 | `docs/run-history.md` | 対象リポジトリの実行履歴 | FR-009 |

## 共通部品

| 部品名 | ファイル | 用途 | 使っている要求 ID |
|---|---|---|---|
| 管理データモデル | `EABK-Studio/eabk_model.py` | 正本ファイルを読み、ノードと関係を構築 | FR-001、FR-009、NFR-OPS-004、NFR-SEC-002 |
| HTTP サーバー | `EABK-Studio/studio.py` | 127.0.0.1 限定の読取 API と静的配信 | FR-010、FR-013、NFR-OPS-003、NFR-SEC-001 |
| ストア | `EABK-Studio/web/js/store.js` | モデル、選択、関連、表現間の状態を共有 | FR-002、FR-003、FR-004、FR-005、FR-006、FR-007、FR-008 |
| UI 部品 | `EABK-Studio/web/js/ui.js` | 表示、詳細、通知、リンク | FR-006、FR-011、NFR-OPS-003、NFR-UX-005、NFR-UX-007 |
| フィンガープリント | `EABK-Studio/studio.py` | 更新検知と再読込 | FR-012、NFR-OPS-002 |
| 起動スクリプト | `EABK-Studio/start.ps1`, `EABK-Studio/start.sh` | Windows/macOS/Linux の起動補助 | NFR-OPS-001 |
| Three.js 同梱モジュールモジュール | `EABK-Studio/web/vendor/three.module.min.js` | 3D マップ表示 | FR-003 |
