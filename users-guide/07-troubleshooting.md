**日本語** | [English](07-troubleshooting.en.md)

# 7. トラブルシューティング

## 7.1 拒否・差し戻し

| 症状（メッセージ） | 原因 | 対処 |
|---|---|---|
| `[G-1] 要求定義書を編集できるのは rd-author だけです` | run の実行中に、rd-author 以外が要求定義書を編集しようとした | 想定どおりの動作です。conductor が rd-author に依頼し直します。利用者が手で直したい場合は、run が終わってから（`work/current-run.txt` がない状態で）編集します |
| 作業役の作業中に `[G-5] conductor が編集できるのは /work/ と docs/run-history.md だけです` が出る | harness が `subagentStart` イベントを発行しておらず、作業役を識別できない（Phase 1 の確認項目 3） | `work/.ebak/gate.log` に `START <作業役>` があるかを確認します。ない場合は、`scripts/ebak.config.json` の `gates.enforce_conductor_edit_scope` を `false` にします（G-1・G-2 は worktree とブランチでも判定するので、主要な保護は維持されます） |
| `[G-2] 作業役は台帳を更新しません` | implementer が `ledger.py run` を `--no-record` なしで実行した | `ledger.py run --cases <ID> --no-record` を使います。台帳は、統合後に conductor が更新します |
| `[G-5] run_options の git_push が「しない」なので push しません` | push が許可されていない | 必要なら、次の依頼で `git_push: 作業ブランチへ push する` を指定します |
| `[G-5] run_options の external_write が「しない」なので、外部のツールでの変更（<ツール名>）はしません` | run 中に、MCP Server・plugin・拡張機能のツールで外部のシステムを変更しようとした（メール送信、チケット作成、リソースの作成など） | 想定どおりの動作です。参照（検索・取得）は続けて行えます。変更が必要なら、次の依頼で `external_write: する` を指定します。名前に動詞を含むが、ローカルにしか作用しないツールが拒否される場合は、`scripts/ebak.config.json` の `gates.external_tool_allow` にツール名の正規表現を追加します（[4.3](04-customization.md#43-ゲートの調整gates)） |
| 社内の情報（Work IQ）や Microsoft Learn・Azure の MCP Server が使われない | その MCP Server・plugin が、run を実行する環境（VS Code・Copilot CLI・GitHub Copilot app）に設定されていない、または VS Code のツールピッカーで無効になっている。agent の frontmatter に `tools:` を追加して、ツールを限定している | VS Code の MCP の一覧（`MCP: List Servers`）、Copilot CLI の `/mcp`、GitHub Copilot app の **カスタマイズ** → **インストール済み** でサーバーが有効かを確認します。サインインが必要なものは事前にサインインします。agent の frontmatter に `tools:` を書いた場合は、`<サーバー名>/*` を追加します（[4.4](04-customization.md#44-mcp-serverplugin拡張機能を使う)） |
| `[G-5] 実行中は git のブランチ名を変更しません` | GitHub Copilot app のセッションで、エージェントがセッションのブランチ名を付け直そうとした（`rename_branch`） | 想定どおりの動作です。統合ブランチ名は run の開始時に記録されているため、そのまま続けます。ブランチ名を変えたい場合は、run の開始前か終了後に行います。画面から変えてしまった場合は、`python scripts/run-state.py status` が現在のブランチを統合ブランチとして記録し直します（`WARN 統合ブランチ … を記録し直しました`） |
| `[G-6] ログ・証跡・実行結果などの一時ファイルは /work/runs/<run-id>/ に書きます` | テストレポートなどをリポジトリ直下に出力しようとした | テストツールの出力先を `work/` の下に設定します（例: Playwright の `outputDir`） |
| `[G-4] 終了前の検証が失敗しています` | 作業役の verify が失敗した | 作業役が自動で修正します。3 回で直らなければ `GATE G-4` 付きで conductor に返され、その項目は統合されません |
| 作業役の書き込みが `[G-5] 作業ディレクトリ外への書き込みは禁止` で拒否され、別の run が `blocked` で終わった | subagent の `sessionId` は親ではなく agentId です（`subagentStart` は `sessionId`=親・`agentId`・`parentAgentId` を持つ）。旧 gate は agentId を「未所有の新しい run」の持ち主と見なして横取りし、束縛後は sibling run を判定できなかった | 配布元の最新 gate.py に更新します（`subagentStart` の親子記録 `work/.ebak/active-agents.json` に一致する agentId だけを親 session とみなし、他 session 所有の run への書き込みは G-5 で拒否します。記録のない id・`subagentStop` 後の id・入れ子（親が agentId）の 2 段目は許可されません）。既に G-5 で finished になった run は再開・done 化せず、必要なら新しい run で依頼し直します。再送で書き込みを通そうとせず、`gate.log` の `START`/`DENY` を確認します |
| 並列 run で、rd-author に依頼したのに `[G-1] 要求定義書を編集できるのは rd-author だけです` が出る | 同時実行の run があると、`subagentStart` の記録（`work/.ebak/active-agents.json`）が別の run の `work/.ebak/` に書かれ、対象 run には rd-author が見えなかった | 最新 gate.py に更新します（記録に `session` を付け、同じセッションが起動した作業役は、別の run の記録でも有効と見なします。他セッションの記録・`session` のない記録は有効になりません）。ゲートの変更・迂回はしません |
| 並列 run で、自分の run なのに `[G-5]`・`[G-1]` が出る。別の run の `gate.log` に自分の書き込みの DENY が残る | 同時に別の session が最初の tool 呼び出しをすると、まだ持ち主のいない新しい run を先に取り込み（R-2）、本来の持ち主が自分の run に束縛されなくなっていた（`meta.json` の `session_id` が別の session になる） | 最新の gate.py・run-state.py に更新します。`run-state.py start` を実行した session を hook が記録し、start が `session_id` に保存するため、取り違えは起きません（claim は start コマンドの識別子と結びつき、start は自分の識別子と一致する claim だけを消費します。追記・消費・`session_id` の記録は `work/.ebak/start-claims.lock` の排他で行います。所有者なし run の救済は、候補が 1 つ・session が特定でき・他 session の未消費 claim がないときだけです）。既に取り違えた run は、`session_id` を持ち主に直さず新しい run で依頼し直します |
| 主の作業ツリーで run を置いたとき、run と無関係な別の chat の編集が `[G-5]` で拒否される | 旧 gate は、持ち主以外の session にも run のゲートを掛けていた | 最新の gate.py に更新します。持ち主と異なる session（識別子あり）には run のゲート（編集範囲・hook の変更禁止・main への commit 禁止・deploy・external_write）を掛けません。G-1〜G-3・G-6・force push の禁止は常に残ります（[6.1.1](06-quality-gates.md#611-主ツリーで-run-を置いたときの別-sessionfr-1076)）。持ち主の chat と所有者なし run は従来どおりゲートが掛かります |
| `/build template` の表示中でない chat の tool が `TEMPLATE` で拒否される／他の chat の発話で制限が早く外れる | 旧 gate は template 状態を 1 ファイルで共有していた | 最新の gate.py に更新します。状態は session ごと（`work/.ebak/template-request-<session>.json`）で、自分の session の次の発話でだけ消えます |
| `[G-5] start-claim を記録できませんでした`／`start-claim・meta の排他を 10 秒以内に得られず、run を始めませんでした` | 別の start・hook が `work/.ebak/start-claims.lock` を保持している | claim・meta は書かれていません。少し待ってもう一度実行します。保持していたプロセスが異常終了していても、ロックは OS が解放する（ロックファイルの残留で止まらない）ので、次の呼び出しがそのまま進みます。work/.ebak/start-claims.lock の中身は保持者の PID（診断用）で、手で消す必要はありません |
| run の worktree への `git -C <worktree> commit`・`cd <worktree>; git commit` が `実行中は main に直接 commit・merge しません` で拒否される | 旧 gate は hook の cwd のブランチだけで判定していた | 最新の gate.py に更新します。`git -C <path>`・`cd <path>` が指す tree のブランチで判定します（main に実際に commit される場合は従来どおり拒否します） |
| hook がまったく動かない | Session Target が Copilot 以外、hook が無効、Python がない | Session Target で Copilot harness を選びます。`/hooks`（VS Code）や `copilot` の設定で hook が有効かを確認します。`python --version` を確認します。`work/.ebak/gate.log` が作成されるかどうかで判断できます |
| GitHub Copilot app で hook の失敗の警告が出る（Windows で `DriveNotFoundException` など） | ローカル サンドボックスの中で PowerShell や Python を起動できなかった。Python がサンドボックスから読めない場所にある | 一時的なものは、`/restart-session` でセッションを再起動すると直ることがあります。続く場合は、プロジェクトのサンドボックス設定の **追加の読み取り専用** に Python のインストール先を追加します。ゲートが効かない間も、verify が統合の時点で同じ規則を検査します |

Windows の core.autocrlf で CRLF になったファイルは、`tools/install.py` が CRLF/LF を正規化して比較するため、改行だけの差では `KEEP-LOCAL` になりません。本物のローカル変更（内容の差）は従来どおり `KEEP-LOCAL` のまま保持されます（`--force` は使いません）。

原因の切り分けのために hook を一時的に止めたい場合は、`scripts/ebak.config.json` の `gates.enabled` を `false` にします（verify の検査は残ります）。終わったら必ず元に戻してください。

## 7.2 run が止まる・終わらない

| 症状 | 対処 |
|---|---|
| Autopilot が途中でターンを終えた | 同じセッションで「続けて」と送信します。新しいセッションの場合は、同じ Prompt を送ると `RESUME` で再開します（GitHub Copilot app の新しい作業ツリーでは、新しいセッションは別の worktree になるので、必ず同じセッションで送ります） |
| GitHub Copilot app で、再開したはずが新しい run（`START`）になった | 新しい作業ツリーのセッションを新しく作ったため、前の worktree の `/work` が見えていない | 新しいセッションの run は `work/current-run.txt` を削除して止め、サイドバーから前のセッションを開いて「続けて」と送ります。前の worktree は `git worktree list` で確認できます |
| GitHub Copilot app を閉じたり PC がスリープしたりして止まった | ローカルのセッションは PC の上で動いている | アプリを起動し直し、同じセッションで「続けて」と送ります。長い run の間は、PC のスリープを無効にします。PC を離れたい場合はクラウド サンドボックスを検討します（[README](../README.md#github-copilot-app-で実行する)） |
| 終わらない（同じ失敗を繰り返している） | `python scripts/run-state.py status` と `progress.md` で、どの項目が何回失敗しているかを確認します。`max_hours` の 85% に達すると、自動的に最終工程に進みます。急ぐ場合は、その項目を `python scripts/run-state.py queue set <ID> --status blocked` にします |
| 「完了条件を満たしていません」で差し戻され続ける | `python scripts/run-state.py complete-check` が出力する理由を確認します。工程 6 を終えて `run-state.py stage 6 --done` を実行し、`run-report.md` を作成する必要があります。差し戻しは 40 回、または時間予算の 125% で止まります |
| 孤児プロセス（node・ブラウザーなど）が残って重い | `python scripts/watch.py scan` で確認し、`python scripts/watch.py reap`（必要なら `--under <PATH>`）で回収します。詳細は [watch.py](05-scripts-reference.md#watchpy) |
| 項目が 60 分を超えて `doing` のまま（`STUCK`） | `python scripts/watch.py stuck` で確認します。conductor は結果を返させるか `integrate.py abandon <item>` で todo に戻します |
| `clean-work.py` が run を `KEEP` する | 全件完了、main 統合、統合後 verify、清掃前版 report、または所有証拠のいずれかが未達です。表示された保持理由を直してください。失敗・中止・未達 run は自動期限なく保持されます |
| `clean-work.py` が非 0 で止まる | dirty、パス衝突、Windows のファイルロック、Git 登録の変化などで候補の削除に失敗しました。run 専用 worktree に未コミット変更があると `run-worktree` と統合ブランチは保持されます（コミットか破棄して再実行）。`run-report.md` の候補別結果を確認し、利用中のファイルを閉じるなど原因を除いて同じコマンドを再実行します。削除済み候補は成功済みとして扱われ、残存候補だけが再検査されます |
| 前の run が残っていて、新しい依頼が RESUME になる | 前の run を終わらせるか、`work/current-run.txt` を削除してから依頼します |
| `LAND-WAIT`（取り込みが待たされる） | 主の作業ツリーが base（main）をチェックアウト中で、その未コミットの変更が取り込む変更と同じファイルに重なっている。変更を commit か退避すると、同じ `run-state.py land` で取り込めます |
| `LAND-CONFLICT`（競合したファイルの一覧つき） | 自動同期（base の取り込み直し）で解消できないファイルがある。run の worktree で `git merge main` して競合を解消し、`verify.py --quick` が通ってから `run-state.py land` を再実行します（`tests/system/ledger.json` だけの競合は自動で解消されます） |
| `gate.log` に `UNBOUND-RUN` | hook が、どの run にもセッションを束縛できなかった（セッション ID があり、所有者のない run が見つからない）。run の worktree を cwd にしてコマンドを実行しているかと、`work/runs/<run-id>/meta.json` の `session_id` を確認します |

## 7.3 verify が失敗する

| 症状 | 対処 |
|---|---|
| `PASS (cached …)` と出るが、結果が古いのではと心配 | キャッシュは、作業ツリーが clean で、HEAD・引数・設定・run の状態が同じときだけ使われます。ビルドの環境（SDK・依存のキャッシュなど）を変えた後は `--no-cache` で再実行します |
| `INTEGRATE: fail <項目> …` が出る | `integrate.py merge` が、verify か System Test の失敗のため統合を取り消し、項目を todo に戻しました。出力の要約を付けて、conductor が implementer に戻します。統合ブランチは統合前の状態のままです |
| インストール直後に CHK-20・CHK-01 が大量に出る | 既存の要求定義書が toolkit の書式になっていないためです。`python scripts/next-id.py --sync --adopt` を実行した後、「既存の要求定義書を toolkit の書式に合わせる。意味は変えない」と依頼します |
| 工程 4 の後に CHK-10/11 が出る | AC が追加・変更されたのに、System Test が追従していません。conductor が test-designer に作業を割り当てます |
| CHK-19 で、テストデータや資料の中の ID が検出される | `checks.id_scan_exclude` にそのパスを追加します |
| CHK-08 でカタログのパスが見つからない | パスはリポジトリのルートからの相対パスで、`src/a.ts, src/b.ts` のようにカンマ区切りで書きます。ファイルの名前を変えた・削除した場合は `python scripts/rdfix.py --apply` が参照を直します |
| マージの後にカタログ・ID 台帳・台帳・実行履歴が食い違う（CHK-07・CHK-01・CHK-11・CHK-23） | `python scripts/rdfix.py --full` で確認し、`python scripts/rdfix.py --full --apply` で直します（終了コード 0 = 合格・修復済み、1 = 手動対応が残る、2 = 実行しなかった・取り消した。インストール時にも既定で実行され、`--no-repair` で止められます。同時に 2 つ適用すると後からのものが最大 30 秒待ち、超えると exit 2。要求定義書は変更しません）。`MANUAL` の行は、表示された担当の役割が直します（[6.3](06-quality-gates.md#63-データ層の不整合の自動修正rdfix)） |
| CI でだけ失敗する | CI にアプリのツールチェーンがない可能性があります。`.github/workflows/ebak-verify.yml` にセットアップのステップを追加します |

## 7.4 Windows 固有の問題

| 症状 | 対処 |
|---|---|
| `python` で Microsoft Store が開く | 実体の Python をインストールし、「アプリ実行エイリアス」の python を無効にします |
| 日本語が文字化けする | スクリプトは UTF-8 で出力します。PowerShell で `$OutputEncoding = [Console]::OutputEncoding = [Text.Encoding]::UTF8` を設定します |
| `verify.ps1` を実行できない | `powershell -ExecutionPolicy Bypass -File scripts/verify.ps1` を使うか、`python scripts/verify.py` を直接実行します |

## 7.5 ログの場所

| 見たいもの | 場所 |
|---|---|
| hook が拒否・差し戻した操作 | `work/.ebak/gate.log` |
| run の進捗と判断 | `work/runs/<run-id>/progress.md` |
| verify・テストのログの全文 | `work/runs/<run-id>/logs/` |
| 監査の生データ | `work/runs/<run-id>/audit/` |
| 過去の run の結果と KPI | `docs/run-history.md` |
