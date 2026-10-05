# HVE の1操作起動（Windows / macOS）

> **状態**: private trial。Windows 11 x64、Apple Silicon macOS 15 / 26 を対象とします。installer、単体 exe / `.app`、署名・公証、匿名公開配布は対象外です。

## 前提

- 認証済みの利用者へ配布された HVE source ZIP を取得します。
- ZIP は書き込み可能な場所へ展開します。取得・展開、OS が直接表示する UAC / `sudo` / CLT / Gatekeeper の確認、GUI 表示後の GitHub / Copilot 認証は「1操作」の対象外です。
- 初回 setup はオンラインで Python、依存パッケージ、GitHub CLI、Node.js、PTY、Copilot runtime 等を取得します。

## 起動

### Windows

1. ZIP を展開します。
2. ZIP 直下の `Start-HVE.cmd` を起動します。
3. Windows の権限確認が表示された場合は、内容を確認して操作します。

対象外の Windows / CPU、壊れた配布物、取得・検証に失敗した依存は GUI を起動せず終了します。Windows PowerShell 5.1 へのフォールバックは行いません。

### macOS

1. ZIP を展開します。
2. ZIP 直下の `Start-HVE.command` を Finder から起動します。
3. macOS の Command Line Tools、権限、Gatekeeper 等の確認が表示された場合は、内容を確認して操作します。

対象は Apple Silicon の macOS 15 / 26 です。Intel Mac、Rosetta、旧 macOS はこの trial の対象外です。

## 初回認証

setup 自体は `gh auth login`、Copilot login、OAuth、ブラウザー、MCP / Plugin の install・enable・config・auth を自動実行しません。GUI が表示された後、必要な機能を利用者が既存の認証導線から明示的に操作します。認証を拒否しても、認証を必要としない GUI は起動できます。

## 2回目以降

起動時の共通 verifier が既存 `.venv` と依存状態を確認します。合格すれば setup を再実行せず GUI を起動します。バージョン差分の判断が必要な場合は `needs_version_decision` として既存の version entrypoint へ進み、いきなり setup を再実行しません。修復が必要な場合も、HVE の `.venv` 以外の Python、`hve/.settings.txt`、`docs/`、`knowledge/`、`qa/`、`src/`、`work/` を bootstrap が削除・上書きしない契約です。

## 失敗時

失敗時は固定 enum の `stage` / `reason_code` を表示して終了します。配布 hash 不一致、critical file 不一致、対象外 OS、依存導入失敗、検証失敗は成功扱いにしません。再実行する場合は、表示された原因を解消して同じ launcher を再度起動します。

## 検証状況

- Windows launcher / verifier の契約・隔離テストは実施済みです。
- macOS workflow は手動・費用承認専用です。実行前に公式単価と run 単位の見積りを再提示します。
- GitHub-hosted macOS runner の成功は clean Mac の証拠にしません。
- Windows 11 clean OS、macOS 15 clean OS、macOS 26 clean OS の受入結果は、各環境で実施するまで `NOT_RUN` です。

## 関連資料

- [GUI Orchestrator はじめかた](hve-gui-getting-started.md)
- [CLI Orchestrator はじめかた](hve-cli-getting-started.md)
- [トラブルシューティング](troubleshooting.md)
