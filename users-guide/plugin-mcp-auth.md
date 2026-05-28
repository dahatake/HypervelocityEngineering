# Plugin / MCP Server 認証ガイド

> ⚠️ **本ドキュメントの位置付け（2026-05-27 現在）**
>
> - **ユーザー影響**: HVE GUI から MCP / Plugin の認証を起動する専用 UI（旧 🔐 ボタン）は廃止されています（[hve/gui/main_window.py](../hve/gui/main_window.py) の該当箇所に「Plugin / MCP Server 認証ボタンは廃止」とコメントあり）。認証は **GitHub Copilot CLI 側で完結** させる運用に移行しました。
> - **実装状況（参考）**: 旧ガイドが参照していた `hve/gui/auth_providers/`（manifest システム）は 2026-02 のコミットで他作業と併せ削除済みです。同じく旧記述の `hve/gui/pty_auth_controller.py` / `hve/gui/pty_auth_session_widget.py` は **過去・現在いずれも本リポジトリに存在しません**。PTY 関連コード（[hve/gui/pty_backend.py](../hve/gui/pty_backend.py) / [hve/gui/widgets/xterm_terminal_view.py](../hve/gui/widgets/xterm_terminal_view.py)）は残存していますが、本番 GUI コードからは現在呼び出されておらず、テスト経由でのみ実行されます。
> - **公式ルート**: 本ドキュメントは現状を整理し、公式 GitHub Copilot CLI の `/mcp add` / `/login` フローに読者を誘導します（公式: <https://docs.github.com/en/copilot/how-tos/copilot-cli/use-copilot-cli/overview>）。

---

## 1. 概要

### 1.1 ユーザー影響サマリ

- GUI から「Plugin / MCP Server 認証ダイアログ」を起動する手段は **現状ありません**。
- MCP サーバの登録・認証は GitHub Copilot CLI 標準の対話 UI（`/mcp add` / `/login` slash command）で行います。
- HVE GUI の設定パネルには、現在登録済みの MCP サーバと Plugin の **一覧表示** 機能のみ残っています（実装: [hve/gui/page_options.py](../hve/gui/page_options.py)、薄いラッパ: [hve/gui/copilot_cli_bridge.py](../hve/gui/copilot_cli_bridge.py)）。

### 1.2 実装状況（参考）

| カテゴリ | パス | 状態 |
|---|---|---|
| 設定パネルから利用中 | [hve/gui/copilot_cli_bridge.py](../hve/gui/copilot_cli_bridge.py) | GitHub Copilot CLI の薄いラッパ。MCP / Plugin 一覧の取得に使用。 |
| 設定パネルから利用中 | [hve/gui/page_options.py](../hve/gui/page_options.py) | 上記ブリッジを呼び出す画面実装。 |
| CLI バイナリ解決 / login | [hve/auth.py](../hve/auth.py) | `find_copilot_binary` / `is_authenticated` / `run_login` を提供。`copilot_cli_bridge.py` が委譲。 |
| 実装は残存・本番未使用 | [hve/gui/pty_backend.py](../hve/gui/pty_backend.py) | PTY 抽象レイヤ。現在は単体テストからのみ参照。 |
| 実装は残存・本番未使用 | [hve/gui/widgets/xterm_terminal_view.py](../hve/gui/widgets/xterm_terminal_view.py) | xterm.js を埋め込んだターミナルウィジェット。同上。 |
| 削除済み（過去存在） | `hve/gui/auth_providers/` 配下 | 2026-02 のコミットで他作業と併せ削除済み（manifest システム）。 |
| 過去・現在いずれも未実装 | `hve/gui/pty_auth_controller.py` / `hve/gui/pty_auth_session_widget.py` | 旧ガイドに記載があったが、git 履歴を含め本リポジトリには存在しません。 |

### 1.3 廃止済み GUI 設定キー

GUI 設定 (`settings.ini`) の `[options]` セクションにあった `mcp_config` / `workiq_tenant_id` は廃止済みです。

- 起動時に `[options]` セクション内の上記キーを検出すると、自動で削除しファイルへ再保存します（実装: [hve/gui/settings_store.py](../hve/gui/settings_store.py) `_OBSOLETE_KEYS` / `_migrate_obsolete_keys`）。マイグレーション対象は `[options]` セクション限定です。
- **GUI フォーム経路は廃止** ([hve/gui/page_options.py](../hve/gui/page_options.py) のコメント「workiq_tenant_id の GUI 入力経路は廃止」参照) ですが、**CLI 引数 `--mcp-config` / `--workiq-tenant-id` および環境変数 `WORKIQ_TENANT_ID` の経路は引き続き有効** です（CLI: [hve/__main__.py](../hve/__main__.py) で argparse 受理 → `_load_mcp_config()` / `cfg.workiq_tenant_id` で消費、環境変数: [hve/config.py](../hve/config.py) `os.environ.get("WORKIQ_TENANT_ID")` で取得）。
- なお i18n ファイル ([hve/gui/i18n/hve_gui_en_US.ts](../hve/gui/i18n/hve_gui_en_US.ts)) には旧ボタン文字列「🔐 PluginやMCP Serverへの認証」が残置されていますが、UI ボタン自体は [hve/gui/main_window.py](../hve/gui/main_window.py) で生成されていません。

---

## 2. 公式ルート: GitHub Copilot CLI での MCP サーバ登録と認証

本章は GitHub Copilot CLI 公式ドキュメントに基づきます（一次情報源: <https://docs.github.com/en/copilot/how-tos/copilot-cli/use-copilot-cli/overview>）。

### 2.1 対話 UI 経由での登録（推奨）

1. ターミナルで `copilot` を起動し、対話セッションに入る。
2. プロンプトで以下の slash command を実行する:

   ```text
   /mcp add
   ```

3. 表示されるフォームに、MCP サーバの起動コマンド・引数・環境変数等を入力し、`Ctrl+S` で保存する。

詳細手順は GitHub Copilot CLI 公式ドキュメント [Using GitHub Copilot CLI](https://docs.github.com/en/copilot/how-tos/copilot-cli/use-copilot-cli/overview) の「Add an MCP server」節を参照してください。

### 2.2 設定保存先

`/mcp add` で登録した内容は以下の場所に JSON として保存されます。

| OS | パス |
|---|---|
| Linux / macOS | `~/.copilot/mcp-config.json` |
| Windows | `%USERPROFILE%\.copilot\mcp-config.json` |

- 環境変数 `COPILOT_HOME` を設定すると保存ディレクトリを変更できます（公式記載）。
- JSON 構造の仕様は GitHub Copilot 公式ドキュメント（<https://docs.github.com/en/copilot>）の MCP 関連ページを参照してください。

### 2.3 認証（`/login`）

GitHub への認証は対話セッション内の `/login` slash command で実施します。詳細は [About GitHub Copilot CLI](https://docs.github.com/en/copilot/concepts/agents/copilot-cli/about-copilot-cli) を参照してください。サービス固有の認証（Azure / GitHub 等）は **各 MCP サーバの実装仕様に依存** します（例: `az login` で取得した資格情報を Azure SDK 経由で利用する等）。具体手順は §2.4 の各サーバ公式情報源を参照してください。

### 2.4 サービス別の参照先

各 MCP サーバの起動コマンド・必要な環境変数・推奨設定は、それぞれの公式リポジトリ／ドキュメントを参照してください。本ドキュメントでは個別の起動コマンド例は記載しません（バージョンや配布形態の変更が頻繁なため）。

| サーバ | 公式情報源 |
|---|---|
| Azure MCP Server | <https://github.com/microsoft/mcp/blob/main/servers/Azure.Mcp.Server/README.md>（旧 `Azure/azure-mcp` リポジトリは 2026-02-06 にアーカイブされ、現在は `microsoft/mcp` モノレポ配下で開発継続中） |
| GitHub MCP Server | <https://github.com/github/github-mcp-server>（Copilot CLI 用インストールガイドは [`docs/installation-guides/install-copilot-cli.md`](https://github.com/github/github-mcp-server/blob/main/docs/installation-guides/install-copilot-cli.md) を参照） |
| Microsoft Work IQ | Microsoft 365 / Microsoft 公式案内に従う（本ドキュメント更新時点で公式 URL の確認手順を本リポジトリに整備していないため、URL の明示を控えます） |
| その他 MCP サーバ | 各サーバの配布元（npm パッケージ・GitHub リポジトリ・コンテナイメージ等） |

### 2.5 非対話セットアップ

CI 等の非対話環境で MCP 設定を投入する場合は、`/mcp add` の対話 UI を経由せず、`mcp-config.json` を直接生成・配置する方法があります（公式 JSON 構造は §2.2 のリンクを参照）。本リポジトリ内に該当用途の自動化スクリプトは確認できませんでした（本ドキュメント更新時点）。

---

## 3. HVE GUI / CLI からの利用

### 3.1 `copilot_cli_bridge.py` の現状

HVE GUI の設定パネル ([hve/gui/page_options.py](../hve/gui/page_options.py)) は、登録済みの MCP サーバと Plugin を一覧表示するために [hve/gui/copilot_cli_bridge.py](../hve/gui/copilot_cli_bridge.py) を呼び出します。ブリッジは内部で以下の Copilot CLI コマンドを実行します（実装ソース参照）。

| 呼び出すコマンド | 用途 |
|---|---|
| `copilot mcp list --json` | 登録済み MCP サーバの一覧取得（`{ "mcpServers": { name: {...} } }` 形式を期待） |
| `copilot mcp get <name> --json` | 個別 MCP サーバの定義取得 |
| `copilot plugin list` | Plugin 一覧取得（`--json` 未対応のため行ベース正規表現で解析） |
| `copilot login` | GitHub Copilot へのログイン（`hve.auth.run_login` 経由） |

> ⚠️ **公式ドキュメントとの差異**: 公式は対話 UI の `/mcp add` slash command と `~/.copilot/mcp-config.json` を一次情報源として推奨しており、本ブリッジが利用する **サブコマンド形式** (`copilot mcp list` / `copilot mcp get` / `copilot plugin list` / `copilot login`) については、本ドキュメント作成時点の公式ドキュメント（<https://docs.github.com/en/copilot/concepts/agents/copilot-cli/about-copilot-cli> 、<https://docs.github.com/en/copilot/how-tos/copilot-cli/use-copilot-cli/overview>）に明記を確認できませんでした。本ブリッジは [hve/gui/copilot_cli_bridge.py](../hve/gui/copilot_cli_bridge.py) のソースコメント記載のターゲットバージョン **Copilot CLI v1.0.48 時点の振る舞い** に基づきます（本リポジトリ内に実機検証エビデンスは保有していません）。Copilot CLI 内部仕様の変更により、出力スキーマやサブコマンドが変更される可能性があります。

### 3.2 廃止済み GUI 設定キーのマイグレーション

[hve/gui/settings_store.py](../hve/gui/settings_store.py) は読み込み時に `[options]` セクションの廃止キーを自動削除します（実装: `_OBSOLETE_KEYS` / `_migrate_obsolete_keys`）。

- 対象セクション: `[options]` のみ。他セクションの同名キーは削除されません。
- 対象キー: `mcp_config` / `workiq_tenant_id`。
- 削除後、`settings.ini` はその場で **再保存** されます。

### 3.3 CLI 引数 / 環境変数経路

GUI フォームから `mcp_config` / `workiq_tenant_id` を入力する経路は廃止されています（[hve/gui/page_options.py](../hve/gui/page_options.py) の「workiq_tenant_id の GUI 入力経路は廃止 (Wave 3 / Q9=b)」コメント参照）。一方、以下の経路は引き続き有効です。

| 経路 | キー / 引数 | 実装位置 |
|---|---|---|
| CLI 引数 | `--mcp-config <path>` | [hve/__main__.py](../hve/__main__.py)（argparse で受理、`_load_mcp_config()` で消費） |
| CLI 引数 | `--workiq-tenant-id <id>` | [hve/__main__.py](../hve/__main__.py)（argparse で受理、`cfg.workiq_tenant_id` に代入） |
| 環境変数 | `WORKIQ_TENANT_ID` | [hve/config.py](../hve/config.py)（`os.environ.get("WORKIQ_TENANT_ID")` で取得） |

各経路の詳細は §1.3 も併せて参照してください。

---

## 4. トラブルシューティング

> 本章は **過去存在した GUI 認証ダイアログ / 将来 PTY 利用 UI が再導入された場合の参考情報** として残しています。現状では GUI からこれらのフローを起動する手段はありません（§1.1 参照）。手元の Copilot CLI / Azure CLI / GitHub CLI を直接利用する場合のヒントとしてもご活用ください。

### 4.1 PTY バックエンドが見つからない

PTY 抽象レイヤ ([hve/gui/pty_backend.py](../hve/gui/pty_backend.py)) が依存する OS ごとのパッケージが未インストールの場合、`PtyBackendError` が発生します。

- **Windows**: `pywinpty>=2.0`（pyproject.toml で宣言。ConPTY 利用）。Windows 10 1809 未満は ConPTY 非対応のため利用できません。
- **Linux / macOS**: `ptyprocess>=0.7`（pyproject.toml で宣言）。

依存をインストールするには、リポジトリで以下を実行してください（`gui-pty` extras は `pyproject.toml` で定義されています）。

```powershell
pip install -e .[gui,gui-pty]
```

### 4.2 xterm.js のアセットが無い

[hve/gui/widgets/xterm_terminal_view.py](../hve/gui/widgets/xterm_terminal_view.py) は xterm.js を埋め込んだ Qt ウィジェットですが、リポジトリのチェックアウト時に vendor 配下が空のままだとロードに失敗します。以下のスクリプトで再取得できます。

```powershell
python tools/fetch_xterm_assets.py
```

### 4.3 Windows で `az` が見つからない

Azure CLI が PATH に追加されている必要があります。インストール後、新しい PowerShell / cmd セッションを開き直してください。Azure CLI の出力フォーマットは時期によって変更されることがあるため、最新版の利用を推奨します（更新手順は Azure CLI 公式ドキュメントに従ってください。検証時点: 2026-05、要再検証）。

### 4.4 検証済みバージョン（参考）

本ドキュメント更新時点 (2026-05、要再検証) の pyproject.toml 宣言と、それに合致する範囲のバージョンを記載します。

| OS | パッケージ | pyproject.toml 宣言 |
|---|---|---|
| Windows | pywinpty | `pywinpty>=2.0; sys_platform == 'win32'` |
| Linux / macOS | ptyprocess | `ptyprocess>=0.7; sys_platform != 'win32'` |

実機での動作確認エビデンスは本リポジトリには保有していません。

### 4.5 機密情報の取り扱い

HVE 自身は **トークンや資格情報を一切保存しません**。Copilot CLI / Azure CLI / GitHub CLI 等のツールが OS の資格情報ストアに保存します（保存先は各 CLI の公式ドキュメント参照）。本リポジトリのログ出力（`hve/gui/workbench_logger.py` 等）に資格情報を自動転送する仕組みはありません。

---

## 5. 関連ドキュメント

### 5.1 外部公式ドキュメント

英語版を一次情報源として採用しています（日本語版は翻訳遅延が発生する場合があります）。

- GitHub Copilot CLI 概要: <https://docs.github.com/en/copilot/concepts/agents/copilot-cli/about-copilot-cli>
- GitHub Copilot CLI 利用ガイド: <https://docs.github.com/en/copilot/how-tos/copilot-cli/use-copilot-cli/overview>
- GitHub MCP Server リポジトリ: <https://github.com/github/github-mcp-server>
- Azure MCP Server（現行）: <https://github.com/microsoft/mcp/blob/main/servers/Azure.Mcp.Server/README.md>

### 5.2 本リポジトリ内ドキュメント

- [HVE GUI Orchestrator ガイド — Plugin / MCP Server 認証](./hve-gui-orchestrator-guide.md#plugin-mcp-server-認証)
- [HVE 技術アーキテクチャ §8 認証と資格情報の取扱い](./hve-technical-architecture.md#8-認証と資格情報の取扱い)

内部コード参照は §1.2 / §3 にまとめています。
