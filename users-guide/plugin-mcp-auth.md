# Plugin / MCP Server インタラクティブ認証ガイド

HVE GUI Orchestrator は **GitHub Copilot CLI を唯一の信頼ソース** として扱い、
CLI が認識している MCP サーバとプラグインの認証状態を一覧表示します。
CLI 側で認証が完了しているサーバはそのまま引き継ぎ、未完了のもののみ、
GUI 内のターミナルで対話的な認証フロー（`az login` / `gh auth login` / Device Flow 等）
を実行します。

本ガイドは以下を対象読者とします:

- `copilot mcp add` で MCP サーバを追加した上で GUI から認証したい開発者
- Azure / GitHub MCP に接続する際の手順を知りたいユーザー
- 自前の MCP サーバ向けに認証 manifest を追加したい上級ユーザー

> **Breaking Change (Wave 3 以降)**: GUI 設定の ``mcp_config`` (MCP Server 設定 JSON
> ファイルパス) と ``workiq_tenant_id`` は **廃止** されました。代わりに
> `copilot mcp add` / `copilot plugin install` で登録してください。既存設定
> ファイルにこれらのキーが残っている場合は、初回起動時に自動削除されます。

---

## 仕組み

> **アーキテクチャ詳細**（OS 認証ストア委譲モデル・PTY 統合・マニフェストスキーマの設計思想・4 ゾーン疎結合境界における位置付け）は [hve-technical-architecture.md §8](./hve-technical-architecture.md#8-認証と資格情報の取扱い) を参照してください。本書は **利用者向けの操作手順** にフォーカスします。

### 概要（要点のみ）

- GUI 認証パネルは **`copilot mcp list --json` / `copilot plugin list` / `copilot login`** を Copilot CLI に問い合わせるだけ。独自のレジストリは持たない。実装は薄いラッパ [hve/gui/copilot_cli_bridge.py](../hve/gui/copilot_cli_bridge.py)。
- HVE 自身は **トークンや資格情報を一切保存しない**。`copilot` / `az` / `gh` 等が OS の資格情報ストア（Windows Credential Manager / macOS Keychain / Linux Secret Service / `~/.azure/`）に保存する。
- 認証ダイアログは PTY（`pywinpty` / `ptyprocess`）+ xterm.js で `az login` / `gh auth login` / `copilot login` 等の対話を埋め込み実行する。

---

## 同梱されている認証 manifest

[hve/gui/auth_providers/manifests/](../hve/gui/auth_providers/manifests/) 配下に YAML として配置されています。

| ID | 対象 MCP サーバ名 | 前提コマンド |
|---|---|---|
| `azure_mcp` | `azure` / `az` / `azure-mcp` | `az login` |
| `github_mcp` | `github` / `github-mcp` | `gh auth login` |
| `_default` | (個別 manifest が無い任意のサーバ) | なし (疎通確認のみ) |

---

## 操作手順

### Azure MCP の認証

1. コマンドラインで Copilot CLI に Azure MCP を登録:

   ```powershell
   copilot mcp add azure-mcp -- npx -y @azure/mcp@latest server start
   ```

2. HVE GUI を起動し、ヘッダの 🔐 「PluginやMCP Serverへの認証」を押す。
3. テーブルに `MCP: azure-mcp` 行が自動掲載されるので、**[認証]** を押す。
4. 新しいダイアログが開き、左にステップ（`az login` など）、右に
   ターミナルが表示される。
5. ターミナル内で規定ブラウザが自動起動するので、Microsoft アカウントで
   サインインする。
6. **サブスクリプション選択画面が出たら**、ターミナルにフォーカスを置いて
   矢印キー（↑ ↓）で対象を選び **Enter**。番号入力でも可。
7. `Subscription is set to ...` が出ると緑色のステップ完了マーカーが付き、
   次のステップへ進む。
8. すべて成功するとダイアログが自動で閉じ、一覧テーブルが ✅ 認証済み に
   更新される。

### GitHub MCP の認証

1. コマンドラインで GitHub MCP を登録 (すでに built-in として含まれている場合もあります):

   ```powershell
   copilot mcp add github --env GITHUB_PERSONAL_ACCESS_TOKEN=ghp_xxx -- npx -y @modelcontextprotocol/server-github
   ```

2. 🔐 ボタン → `MCP: github` 行の **[認証]**。
3. ターミナルで `gh auth login` の対話メニュー（GitHub.com か GHES か、
   ブラウザ認証 or トークン認証）が表示される。**矢印 + Enter** で選択。
4. ブラウザに 8 桁の確認コードを貼り付けて承認すれば完了。

### Microsoft Work IQ の認証

`copilot plugin list` に `workiq@work-iq` が表示されている場合、GUI に
`Microsoft Work IQ` 行が自動掲載されます。

```powershell
# 未インストールであれば事前に:
copilot plugin install work-iq/workiq
```

GUI 上で **[認証]** を押すと `@microsoft/workiq accept-eula` + `ask -q ping` の
シーケンスで状態を確定します。

### 任意の MCP サーバ（manifest 不在の場合）

`_default` manifest がフォールバックとして発動します:

- 前提コマンドは実行されません。
- サーバ固有の認証（API キー / 環境変数 / 個別ログイン）は**事前に**完了させてください。
- ダイアログは **疎通確認のみ** を実施します。

---

## カスタム manifest の追加

自前の MCP サーバ向けに新規 manifest を作成する場合の手順です。

### 配置場所

2 通り対応:

1. **同梱**: [hve/gui/auth_providers/manifests/](../hve/gui/auth_providers/manifests/)
   に `<name>.yml` を直接追加（リポジトリにコミット）。
2. **ユーザー固有**: 環境変数 `HVE_AUTH_MANIFESTS_DIR` を任意ディレクトリに
   設定し、その中に YAML を配置（同名 `id` があれば**ユーザー側が優先**）。

### スキーマ

```yaml
id: my_mcp                              # 一意 ID (必須)
display_name: "My MCP"

match:                                  # 最低 1 つ必須
  mcp_server_name_regex: "^my(_|-)?mcp$"

pre_auth_commands:                      # 順次 PTY 実行
  - argv: ["my-cli", "login"]
    success_regex: "Logged in"
    failure_regex: "(?i)(error|denied)"
    timeout: 600

main_command:                           # 任意
  argv: ["copilot", "-p", "list my_mcp tools", "--allow-all-tools", "--no-ask-user"]
  success_regex: "(?i)available"
  timeout: 300

success_regex: "(?i)tools? (available|registered)"
failure_regex: "(?i)(unauthorized|forbidden)"
timeout_total: 900

notes_md: |
  ## My MCP 認証手順

  1. ...
```

全フィールドの詳細は [hve/gui/auth_providers/manifests/__init__.py](../hve/gui/auth_providers/manifests/__init__.py)
の docstring を参照してください。

### バリデーション

manifest の YAML を保存後、以下のコマンドで構文検証ができます:

```powershell
python -c "from hve.gui.auth_providers.manifests import load_all_manifests; [print(m.id) for m in load_all_manifests()]"
```

構文エラーがある manifest は **個別に skip** され、他の manifest には影響しません。

---

## トラブルシューティング

### Q. ダイアログが「PTY backend not available」と出る

依存パッケージが未インストールです:

```powershell
pip install -e .[gui,gui-pty]
```

Windows なら `pywinpty>=2.0` (ConPTY)、POSIX なら `ptyprocess>=0.7` が必要です。
Windows 10 1809 未満は ConPTY 非対応のため利用できません。

### Q. xterm.js のアセットが無いというエラー

リポジトリのチェックアウト時に vendor 配下が空のままだと発生します。
以下で再取得してください:

```powershell
python tools/fetch_xterm_assets.py
```

### Q. `az login` のサブスクリプション選択画面でキー入力が反映されない

- ターミナルウィジェットにマウスでフォーカスを置いてください。
- それでも反応しない場合、`az` のバージョンが古い可能性があります。
  `az upgrade` を実行してください。

### Q. Windows で `az` が見つからないと言われる

- Azure CLI が PATH に追加されている必要があります。インストール後、新しい
  PowerShell / cmd セッションを開き直してから HVE GUI を再起動してください。
- 検証済みバージョン: Azure CLI v2.50 系（`success_regex` パターンも本バージョン
  の出力に基づきます）。古いバージョンや将来バージョンでは出力文言が変わる場合が
  あるため、ヒットしないときはご自身の manifest を `HVE_AUTH_MANIFESTS_DIR` 経由で
  追加して上書きしてください。

### Q. PTY バックエンドの検証済みバージョン

| OS | パッケージ | 検証済みバージョン |
|---|---|---|
| Windows | pywinpty | 3.0.3 (3.x 系) |
| Linux / macOS | ptyprocess | 0.7+ (未実機検証、API 互換) |

### Q. すでに別端末で `az login` 済みで再認証したくない

該当ステップ実行中に「**次へスキップ**」を押すと、当該ステップを成功扱いで
次のステップへ進められます。

### Q. 機密情報がログに残らないか心配

`PtyAuthSessionWidget` はダイアログを閉じるとターミナル表示を**破棄**します。
出力は `workbench_logger` 等への自動転送もしていません（明示的なユーザー操作
のみ）。トークン / Device Flow コード等を保存する仕組みは無いため、
スクリーンショットや手動コピーをしない限り永続化されません。

---

## 関連

- [HVE GUI Orchestrator ガイド](./hve-gui-orchestrator-guide.md#plugin--mcp-server-認証)
- [hve/gui/pty_backend.py](../hve/gui/pty_backend.py) — PTY 抽象レイヤ
- [hve/gui/widgets/xterm_terminal_view.py](../hve/gui/widgets/xterm_terminal_view.py) — ターミナルウィジェット
- [hve/gui/pty_auth_controller.py](../hve/gui/pty_auth_controller.py) — 認証フロー制御
- [hve/gui/pty_auth_session_widget.py](../hve/gui/pty_auth_session_widget.py) — UI ダイアログ
