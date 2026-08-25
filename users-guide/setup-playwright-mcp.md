# GitHub Copilot CLI への Playwright (MCP) 導入手順書

← [README](../README.md)

> 本書は GitHub Copilot CLI から Playwright によるブラウザ自動化機能を利用できるようにするための、MCP (Model Context Protocol) サーバー登録手順をまとめたものです。
> 対象: `https://github.com/microsoft/playwright` 本体ではなく、その公式 MCP ラッパー `@playwright/mcp` (`https://github.com/microsoft/playwright-mcp`) を Copilot CLI に登録します。
>
> **実装照合 (2026-08-13 更新)**: 本リポジトリの `.github/.mcp.json` には `azure` / `microsoft-learn` のみが登録されており、`playwright` MCP は未登録です（`context7` は 2026-08-13 に削除しました）。Playwright E2E は `playwright.config.js` と `src/test/ui/**/e2e/*.spec.js` に配線済みですが、`.github/.mcp.json` 経由の Playwright MCP とは別物です。

---

## 1. 前提条件

- **GitHub Copilot サブスクリプション**（有効なもの）
- **Node.js 22 以上**（Copilot CLI を npm で導入する場合の要件 / Playwright MCP 自体は公式 README 上 Node.js 18+）
- **PowerShell 6 以上**（Windows の場合）
- ネットワーク経由で `npx` から `@playwright/mcp@latest` を取得可能であること
- 組織/Enterprise で Copilot CLI および MCP サーバーの allowlist ポリシーにより `@playwright/mcp` が許可されていること（企業環境の場合）

## 2. GitHub Copilot CLI のインストール

Windows（PowerShell）では以下のいずれか。

```powershell
# WinGet（推奨）
winget install GitHub.Copilot

# もしくは npm 経由（全 OS 共通）
npm install -g @github/copilot
```

インストール確認:

```powershell
copilot --version
```

## 3. Copilot CLI 起動と認証

```powershell
copilot
```

- 初回は `/login` スラッシュコマンドで GitHub 認証を実施
- PAT を使う場合は `COPILOT_GITHUB_TOKEN` / `GH_TOKEN` / `GITHUB_TOKEN` 環境変数に「Copilot Requests」権限付き fine-grained PAT を設定（優先順もこの順）。トークン値は設定例やログに書かない

## 4. Playwright ブラウザバイナリの事前準備（任意・推奨）

初回利用時に MCP 経由で自動取得されることもありますが、明示的に入れておくと安定します。

```powershell
npx playwright install
```

## 5. Playwright MCP サーバーを登録する（3 つの方法）

### 方法 A: `/mcp add` を使う対話式登録（推奨）

1. Copilot CLI を起動し、対話モードで以下を入力:
   ```
   /mcp add
   ```
2. フォームを `Tab` キーで移動しながら下記を入力:
   - **Server Name**: `playwright`
   - **Server Type**: `Local`（または `STDIO`。VS Code 等と設定共有したい場合は `STDIO` を選択）
   - **Command**: `npx @playwright/mcp@latest`
   - **Environment Variables**: 空 `{}`（必要に応じて）
   - **Tools**: `*`（全ツールを公開）
3. `Ctrl + S` で保存。CLI 再起動不要で即時利用可能。

### 方法 B: `copilot mcp add` サブコマンドを使う

公式ドキュメントでは、対話 UI を使わずに端末から登録する方法も案内されています。

```powershell
copilot mcp add playwright -- npx @playwright/mcp@latest
```

環境変数が必要な MCP サーバでは `--env KEY=VALUE` を使えますが、Playwright MCP の標準設定では通常不要です。

### 方法 C: 設定ファイルを直接編集

設定ファイルパス:

- Windows: `C:\Users\<ユーザー名>\.copilot\mcp-config.json`
- macOS / Linux: `~/.copilot/mcp-config.json`

存在しなければ新規作成し、以下を記述:

```json
{
  "mcpServers": {
    "playwright": {
      "type": "local",
      "command": "npx",
      "args": ["@playwright/mcp@latest"],
      "env": {},
      "tools": ["*"]
    }
  }
}
```

既に他の `mcpServers` エントリがある場合は、その中に `"playwright": { ... }` を追記してください（JSON 構文を壊さないこと）。

> **プロジェクト単位設定**: Copilot CLI 公式の自動ロード対象は `.mcp.json` または `.github/mcp.json` です。本リポジトリの `.github/.mcp.json` は HVE / SDK に `--mcp-config` で渡すためのファイルで、Copilot CLI 公式の自動ロードパスではありません。リポジトリへ Playwright MCP を共有設定として追加する場合は、別タスクで公式パス・信頼設定・組織 allowlist を確認してください。

## 6. 登録の確認

Copilot CLI 内で:

```
/mcp show
```

→ 一覧に `playwright` が表示されること

```
/mcp show playwright
```

→ ステータスが正常で、`browser_navigate`, `browser_click`, `browser_snapshot` などのツールが列挙されること

## 7. 動作確認（スモークテスト）

Copilot CLI のプロンプトで例:

```
Playwright MCP を使って https://example.com を開き、ページタイトルを取得して
```

- ブラウザがヘッドレス起動し、タイトルが返ってくれば成功

## 8. オプション設定（必要に応じて）

特定ブラウザ固定（例: Microsoft Edge）にしたい場合、`args` を変更:

```json
"args": ["@playwright/mcp@latest", "--browser", "msedge"]
```

ヘッドフル表示で動作させたい場合:

```json
"args": ["@playwright/mcp@latest", "--headed"]
```

その他オプションは `npx @playwright/mcp@latest --help` で確認できます。

## 9. 管理用コマンド

| 目的 | コマンド |
|---|---|
| 一覧表示 | `/mcp show` |
| 詳細表示 | `/mcp show playwright` |
| 設定編集 | `/mcp edit playwright` |
| 削除 | `/mcp delete playwright` |
| 端末から一覧表示 | `copilot mcp list`（JSON が必要なら `--json`） |
| 端末から詳細表示 | `copilot mcp get playwright`（JSON が必要なら `--json`） |
| 端末から削除 | `copilot mcp remove playwright` |

## 10. トラブルシューティング

- **`npx` が見つからない**: Node.js 未インストール／PATH 未設定。Node.js 22+ を入れ直す
- **ブラウザ起動失敗**: `npx playwright install` を再実行
- **企業環境で起動できない**: Organization / Enterprise の MCP allowlist ポリシーで `@playwright/mcp` が許可されているか管理者に確認
- **設定ファイルが反映されない**: JSON 構文エラーの可能性。`/mcp show` でエラーが出る場合は `mcp-config.json` を見直す
- **プロキシ環境**: `HTTPS_PROXY` / `HTTP_PROXY` 環境変数を設定してから `copilot` を起動
- **HVE の E2E と混同している**: `playwright.config.js` は `src/test/ui/**/*.spec.js` を実行する通常の Playwright Test 設定です。Copilot CLI にブラウザ操作ツールを追加する Playwright MCP とは登録経路が異なります。

## 11. 参考リンク

- 本リポジトリ内: MCP Server 全般の認証設定とトラブルシュート — [plugin-mcp-auth.md](./plugin-mcp-auth.md)
- GitHub 公式: Adding MCP servers for GitHub Copilot CLI
  <https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/add-mcp-servers>
- About GitHub Copilot CLI
  <https://docs.github.com/en/copilot/concepts/agents/copilot-cli/about-copilot-cli>
- Installing GitHub Copilot CLI
  <https://docs.github.com/en/copilot/how-tos/copilot-cli/set-up-copilot-cli/install-copilot-cli>
- Authenticating GitHub Copilot CLI
  <https://docs.github.com/en/copilot/how-tos/copilot-cli/set-up-copilot-cli/authenticate-copilot-cli>
- Playwright MCP リポジトリ
  <https://github.com/microsoft/playwright-mcp>
- Playwright 本体
  <https://github.com/microsoft/playwright>
- GitHub MCP Registry
  <https://github.com/mcp>

---

**最終更新**: 2026-08-07
