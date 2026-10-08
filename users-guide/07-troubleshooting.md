# 7. トラブルシューティング

## 7.1 拒否・差し戻し

| 症状（メッセージ） | 原因 | 対処 |
|---|---|---|
| `[G-1] 要求定義書を編集できるのは rd-author だけです` | run の実行中に、rd-author 以外が要求定義書を編集しようとした | 想定どおりの動作です。conductor が rd-author に依頼し直します。利用者が手で直したい場合は、run が終わってから（`work/current-run.txt` がない状態で）編集します |
| 作業役の作業中に `[G-5] conductor が編集できるのは /work/ と docs/run-history.md だけです` が出る | harness が `subagentStart` イベントを発行しておらず、作業役を識別できない（Phase 1 の確認項目 3） | `work/.hve/gate.log` に `START <作業役>` があるかを確認します。ない場合は、`scripts/hve.config.json` の `gates.enforce_conductor_edit_scope` を `false` にします（G-1・G-2 は worktree とブランチでも判定するので、主要な保護は維持されます） |
| `[G-2] 作業役は台帳を更新しません` | implementer が `ledger.py run` を `--no-record` なしで実行した | `ledger.py run --cases <ID> --no-record` を使います。台帳は、統合後に conductor が更新します |
| `[G-5] run_options の git_push が「しない」なので push しません` | push が許可されていない | 必要なら、次の依頼で `git_push: 作業ブランチへ push する` を指定します |
| `[G-5] run_options の external_write が「しない」なので、外部のツールでの変更（<ツール名>）はしません` | run 中に、MCP Server・plugin・拡張機能のツールで外部のシステムを変更しようとした（メール送信、チケット作成、リソースの作成など） | 想定どおりの動作です。参照（検索・取得）は続けて行えます。変更が必要なら、次の依頼で `external_write: する` を指定します。名前に動詞を含むが、ローカルにしか作用しないツールが拒否される場合は、`scripts/hve.config.json` の `gates.external_tool_allow` にツール名の正規表現を追加します（[4.3](04-customization.md#43-ゲートの調整gates)） |
| 社内の情報（Work IQ）や Microsoft Learn・Azure の MCP Server が使われない | その MCP Server・plugin が、run を実行する環境（VS Code・Copilot CLI・GitHub Copilot app）に設定されていない、または VS Code のツールピッカーで無効になっている。agent の frontmatter に `tools:` を追加して、ツールを限定している | VS Code の MCP の一覧（`MCP: List Servers`）、Copilot CLI の `/mcp`、GitHub Copilot app の **カスタマイズ** → **インストール済み** でサーバーが有効かを確認します。サインインが必要なものは事前にサインインします。agent の frontmatter に `tools:` を書いた場合は、`<サーバー名>/*` を追加します（[4.4](04-customization.md#44-mcp-serverplugin拡張機能を使う)） |
| `[G-5] 実行中は git のブランチ名を変更しません` | GitHub Copilot app のセッションで、エージェントがセッションのブランチ名を付け直そうとした（`rename_branch`） | 想定どおりの動作です。統合ブランチ名は run の開始時に記録されているため、そのまま続けます。ブランチ名を変えたい場合は、run の開始前か終了後に行います。画面から変えてしまった場合は、`python scripts/run-state.py status` が現在のブランチを統合ブランチとして記録し直します（`WARN 統合ブランチ … を記録し直しました`） |
| `[G-6] ログ・証跡・実行結果などの一時ファイルは /work/runs/<run-id>/ に書きます` | テストレポートなどをリポジトリ直下に出力しようとした | テストツールの出力先を `work/` の下に設定します（例: Playwright の `outputDir`） |
| `[G-7] scripts/hve.config.json の models で <役割> のモデルは <モデル> です` | run の実行中に、conductor が `models` に値のある作業役を、`task` の `model` 引数なし、または違うモデルで呼んだ | 想定どおりの動作です。conductor が指定のモデルで呼び直します。harness の `task` が `model` を受け付けず、呼び直しても拒否が続く場合は、`gates.enforce_models` を `false` にし、agent の frontmatter の `model:` で固定します（[4.2](04-customization.md#42-モデルの割り当てmodels)） |
| `[G-4] 終了前の検証が失敗しています` | 作業役の verify が失敗した | 作業役が自動で修正します。3 回で直らなければ `GATE G-4` 付きで conductor に返され、その項目は統合されません |
| hook がまったく動かない | Session Target が Copilot 以外、hook が無効、Python がない | Session Target で Copilot harness を選びます。`/hooks`（VS Code）や `copilot` の設定で hook が有効かを確認します。`python --version` を確認します。`work/.hve/gate.log` が作成されるかどうかで判断できます |
| GitHub Copilot app で hook の失敗の警告が出る（Windows で `DriveNotFoundException` など） | ローカル サンドボックスの中で PowerShell や Python を起動できなかった。Python がサンドボックスから読めない場所にある | 一時的なものは、`/restart-session` でセッションを再起動すると直ることがあります。続く場合は、プロジェクトのサンドボックス設定の **追加の読み取り専用** に Python のインストール先を追加します。ゲートが効かない間も、verify が統合の時点で同じ規則を検査します |

原因の切り分けのために hook を一時的に止めたい場合は、`scripts/hve.config.json` の `gates.enabled` を `false` にします（verify の検査は残ります）。終わったら必ず元に戻してください。

## 7.2 run が止まる・終わらない

| 症状 | 対処 |
|---|---|
| Autopilot が途中でターンを終えた | 同じセッションで「続けて」と送信します。新しいセッションの場合は、同じ Prompt を送ると `RESUME` で再開します（GitHub Copilot app の新しい作業ツリーでは、新しいセッションは別の worktree になるので、必ず同じセッションで送ります） |
| GitHub Copilot app で、再開したはずが新しい run（`START`）になった | 新しい作業ツリーのセッションを新しく作ったため、前の worktree の `/work` が見えていない | 新しいセッションの run は `work/current-run.txt` を削除して止め、サイドバーから前のセッションを開いて「続けて」と送ります。前の worktree は `git worktree list` で確認できます |
| GitHub Copilot app を閉じたり PC がスリープしたりして止まった | ローカルのセッションは PC の上で動いている | アプリを起動し直し、同じセッションで「続けて」と送ります。長い run の間は、PC のスリープを無効にします。PC を離れたい場合はクラウド サンドボックスを検討します（[README](../README.md#github-copilot-app-で実行する)） |
| 終わらない（同じ失敗を繰り返している） | `python scripts/run-state.py status` と `progress.md` で、どの項目が何回失敗しているかを確認します。`max_hours` の 85% に達すると、自動的に最終工程に進みます。急ぐ場合は、その項目を `python scripts/run-state.py queue set <ID> --status blocked` にします |
| 「完了条件を満たしていません」で差し戻され続ける | `python scripts/run-state.py complete-check` が出力する理由を確認します。工程 6 を終えて `run-state.py stage 6 --done` を実行し、`run-report.md` を作成する必要があります。差し戻しは 40 回、または時間予算の 125% で止まります |
| 前の run が残っていて、新しい依頼が RESUME になる | 前の run を終わらせるか、`work/current-run.txt` を削除してから依頼します |

## 7.3 verify が失敗する

| 症状 | 対処 |
|---|---|
| `PASS (cached …)` と出るが、結果が古いのではと心配 | キャッシュは、作業ツリーが clean で、HEAD・引数・設定・run の状態が同じときだけ使われます。ビルドの環境（SDK・依存のキャッシュなど）を変えた後は `--no-cache` で再実行します |
| `INTEGRATE: fail <項目> …` が出る | `integrate.py merge` が、verify か System Test の失敗のため統合を取り消し、項目を todo に戻しました。出力の要約を付けて、conductor が implementer に戻します。統合ブランチは統合前の状態のままです |
| インストール直後に CHK-20・CHK-01 が大量に出る | 既存の要求定義書が toolkit の書式になっていないためです。`python scripts/next-id.py --sync --adopt` を実行した後、「既存の要求定義書を toolkit の書式に合わせる。意味は変えない」と依頼します |
| 工程 4 の後に CHK-10/11 が出る | AC が追加・変更されたのに、System Test が追従していません。conductor が test-designer に作業を割り当てます |
| CHK-19 で、テストデータや資料の中の ID が検出される | `checks.id_scan_exclude` にそのパスを追加します |
| CHK-08 でカタログのパスが見つからない | パスはリポジトリのルートからの相対パスで、`src/a.ts, src/b.ts` のようにカンマ区切りで書きます。ファイルの名前を変えた・削除した場合は `python scripts/rdfix.py --apply` が参照を直します |
| マージの後にカタログ・ID 台帳・台帳・実行履歴が食い違う（CHK-07・CHK-01・CHK-11・CHK-23） | `python scripts/rdfix.py` で修正の計画を確認し、`python scripts/rdfix.py --apply` で直します。`MANUAL` の行は、表示された担当の役割が直します（[6.3](06-quality-gates.md#63-データ層の不整合の自動修正rdfix)） |
| CI でだけ失敗する | CI にアプリのツールチェーンがない可能性があります。`.github/workflows/hve-verify.yml` にセットアップのステップを追加します |

## 7.4 Windows 固有の問題

| 症状 | 対処 |
|---|---|
| `python` で Microsoft Store が開く | 実体の Python をインストールし、「アプリ実行エイリアス」の python を無効にします |
| 日本語が文字化けする | スクリプトは UTF-8 で出力します。PowerShell で `$OutputEncoding = [Console]::OutputEncoding = [Text.Encoding]::UTF8` を設定します |
| `verify.ps1` を実行できない | `powershell -ExecutionPolicy Bypass -File scripts/verify.ps1` を使うか、`python scripts/verify.py` を直接実行します |

## 7.5 ログの場所

| 見たいもの | 場所 |
|---|---|
| hook が拒否・差し戻した操作 | `work/.hve/gate.log` |
| run の進捗と判断 | `work/runs/<run-id>/progress.md` |
| verify・テストのログの全文 | `work/runs/<run-id>/logs/` |
| 監査の生データ | `work/runs/<run-id>/audit/` |
| 過去の run の結果と KPI | `docs/run-history.md` |
