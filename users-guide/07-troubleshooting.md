**日本語** | [English](07-troubleshooting.en.md)

# 7. トラブルシューティング

## 7.1 verify・CI が失敗する

| 症状 | 対処 |
|---|---|
| `python scripts/verify.py` が exit 1 | 出力の `ERROR CHK-xx <位置> <内容>` を上から直します。各 CHK の直し方は [6.3](06-quality-gates.md#63-verify-の検査項目) にあります。ログの全文は `/work/logs/` にあります |
| `HINT rdfix: …` の行が出る | 自動で直せる不整合があります。`python scripts/rdfix.py --full` で計画を確かめ、`python scripts/rdfix.py --full --apply` で直します（[7.2](#72-データ層の食い違いrdfix)） |
| CI の ebak-verify がデータ層の検査で失敗する | CI は修復しません。手元で `python scripts/rdfix.py --full --apply` を実行し、修復を同じ変更に含めて push し直します（[7.2](#72-データ層の食い違いrdfix)） |
| 手元では合格するのに、CI の ebak-verify だけが失敗する | CI にアプリのツールチェーンがない可能性があります。`.github/workflows/ebak-verify.yml` の verify のステップの前に、セットアップのステップ（`actions/setup-node` など）を追加します。`checks.profile` を手元のコマンドの `--profile` で上書きしていないかも確かめます |
| `PASS (cached …)` と出るが、結果が古いのではと心配 | キャッシュは、作業ツリーが clean で、HEAD・引数・設定が同じときだけ使われます。ビルドの環境（SDK・依存）を変えた後は `--no-cache` で再実行します |
| `FAIL config` | `verify.commands` に `run` のない要素や不正な要素があります。[4.6](04-customization.md#46-ビルド静的解析テストのコマンドverifycommands) の形式に直します |
| `--profile full` で大量の warn が出る | full は書式の警告（CHK-13 曖昧な語、CHK-14 数値の直書き、CHK-15 禁止同義語など）も報告します。warn は終了コードに影響しません。節目の監査に合わせて少しずつ直します |
| インストール直後に CHK-01・CHK-20 が大量に出る | 既存の要求定義書が toolkit の書式になっていません。`python scripts/next-id.py --sync --adopt` を実行し、Copilot に「既存の要求定義書を toolkit の書式に合わせる。意味は変えない」と依頼します（既存のアプリは [10](10-adopting-existing-apps.md)） |
| CHK-19 で、テストデータや資料の中の ID が検出される | `scripts/ebak.config.json` の `checks.id_scan_exclude` にそのパス（glob）を追加します。リストは既定値と結合されず置き換わるので、既定値（`scripts/ebaklib.py` の `DEFAULT_CONFIG`）をコピーしてから足します |
| CHK-08 でカタログのパスが見つからない | パスはリポジトリのルートからの相対パスで、`src/a.ts, src/b.ts` のようにカンマ区切りで書きます。ファイルの名前を変えた・削除した場合は `python scripts/rdfix.py --apply` が参照を直します |
| CHK-10・CHK-11 が出る（AC と台帳のずれ） | AC が追加・変更されたのに、System Test の台帳が追従していません。ケースを足すか見直し、`python scripts/ledger.py digests --update` を実行します。台帳は `ledger.py` でだけ更新します |
| CHK-12 が出る | 台帳のケースの削除や、理由のない変更、`tests/system` の assert の減少があります。元に戻し、変更は `ledger.py update --reason "…"` で理由を残して行います |

## 7.2 データ層の食い違い（rdfix）

マージの後などにカタログ・ID 台帳・台帳が食い違ったときは（CHK-07・CHK-01・CHK-11）、`python scripts/rdfix.py --full` で確認し、`python scripts/rdfix.py --full --apply` で直します。要求定義書は変更しません。

| 終了コード | 意味 | 次にすること |
|---|---|---|
| 0 = 合格・修復済み | 自動で直せるものは残っていない | 差分を確かめて commit します（rdfix は commit しません） |
| 1 = 手動の対応が残る・計画がある | `MANUAL` の行がある、`--apply` なしで計画だけを出した、収束しなかった | `MANUAL … （担当: …）次の行動: …` の行に従って直します。担当は作業の種類（`要求定義書`・`System Test の台帳`・`コードとカタログ`・`リポジトリ`）です |
| 2 = 実行しなかった・取り消した | 下の表のどれか。変更はすべて元に戻っています | 原因を除いて同じコマンドを再実行します |

exit 2 になる主な原因:

| メッセージ・状況 | 対処 |
|---|---|
| 排他の待ち時間切れ（`work/.ebak/rdfix.lock`） | 別の `--apply` が実行中です。終わるのを待って再実行します（待ちは `--lock-wait` 秒、既定 30 秒）。異常終了したプロセスのロックは自動で引き継がれます |
| 書き込みの失敗・要求定義書や `docs/integrations.md` の変化・新しいエラー | すべての変更を元に戻しました。エディターでファイルを開いたままにしていないかを確かめます。元に戻せなかったファイルは `work/.ebak/rdfix-undo-*/` に修復前の内容が保存されます |

## 7.3 複数の人・PC で ID が衝突した

2 つのブランチで同時に `next-id.py` を実行すると、同じ ID が採番されることがあります。マージすると、ID 台帳は `merge=union` で両方の行が残り、CHK-01（ID の重複）が検出します。

1. 後からマージする側のブランチで、衝突した方の要求・AC に `python scripts/next-id.py <種別>` で新しい ID を採番し、要求定義書・テスト・カタログの参照を書き換えます。手で番号を振りません。
2. `python scripts/rdfix.py --full --apply` で ID 台帳の重複行を整理し、`python scripts/verify.py` を exit 0 にします。
3. 予防: 採番の前に base のブランチ（`main`）を取り込みます。`next-id.py` は base のブランチの ID も見て次の番号を決めます。

## 7.4 インストール・更新

| 症状 | 対処 |
|---|---|
| 更新で `KEEP-LOCAL <ファイル>` が出る | ローカルで変更した toolkit のファイルは上書きしません。新しい版を取り込むなら、`--dry-run` で確かめてから差分を手でマージするか、`--force`（`.ebak-backup-*` を残します）を使います。Windows の `core.autocrlf` による改行だけの差では `KEEP-LOCAL` になりません |
| 更新で「この版が配布しないファイルが N 件残っています」と出る | 旧版が入れたファイルです。通常の更新では削除しません。`--clean`（クリーンインストール）で入れ直します（[9.4](09-versioning.md#94-旧版から更新するクリーンインストール)） |
| `--clean の前に、未 commit の変更を commit するか退避します` と出る | `git status` で確かめ、commit するか `git stash` してから再実行します。消したファイルを git から戻せるようにするため、作業ツリーがきれいなときだけ実行します |
| `WARN-WIRING <ファイル>:<行>` が出る | `scripts/*.py` に直接足した独自の検査が、更新で脱落します。`extensions.checks` か `scripts/ext/` に登録し直します（[4.7](04-customization.md#47-プロジェクト固有の検査extensionschecks--scriptsext)） |
| 導入後のデータ層の修復を止めたい | `--no-repair` で検査と計画だけ（書き込まない）、`--skip-verify` で検査も修復もしません。PowerShell のラッパーでは `-NoRepair` です。インストーラの終了コードはデータ層の結果に左右されません |

### 0.5.x から 0.6.0（EABK Lite）に更新したとき

- **更新の方法**: インストーラは旧版からの移行の処理を持ちません。`--clean` でクリーンインストールします。旧版の agent・skill・hook・スクリプト・自動修復のワークフロー・設定の旧キーは、変更していても削除され、この版が入れ直されます。
- **設定**: `scripts/ebak.config.json` は既定から作り直されます。以前の値（`verify.commands` など）は `git diff scripts/ebak.config.json` で確かめ、必要な値を戻します。
- **残るもの**: 管理データ（要求定義書・カタログ・台帳・ID 台帳）と `/work` は変えません。0.5.x の `docs/run-history.md` と `.github/ebak-prompt-prefix.md` も残りますが、もう読みません。不要なら手で削除します。
- **worktree と作業用のブランチ**: 0.5.x の run が残した worktree と `work/*` ブランチは、自動では消しません。`git worktree list` と `git branch --list "work/*"` で確かめ、不要なものを `git worktree remove <パス>` と `git branch -D <ブランチ>` で手で削除します。`/work` の下の古い run のフォルダーも、不要なら削除します。

## 7.5 旧版の hook と定型文

EABK Lite には hook も定型文の自動付与もありません。次は旧版から更新したときの症状です。

| 症状 | 対処 |
|---|---|
| すべてのツールの呼び出しが拒否される・hook の失敗の警告が出る | 旧版の hook のファイル（`.github/hooks/*.json`）が残り、削除された `scripts/hooks/gate.py` を呼んでいます。`--clean` で入れ直すか、ファイルを削除してから Copilot のセッションを開き直します |
| 定型文が付かなくなった | 仕様です。`.github/ebak-prompt-prefix.md` と設定の `prompt_prefix` はもう使いません。毎回伝えたい前提は、自分の Copilot の instructions に書きます |

## 7.6 HVE Studio

| 症状 | 対処 |
|---|---|
| 起動せずに終了コード 1 で終わる（`no EABK data layer … and nothing to show in code mode`） | `--repo` に指定したフォルダーにデータ層（要求定義書など）がなく、コードのモードでも表示するものがありません。コードのモードは git リポジトリのルートだけが対象で、空のフォルダーや git でないフォルダーは表示しません。`python HVE-Studio/studio.py --check --repo <パス>` で、読めたファイルと件数（コードのモードなら `mode: code (...)` の行）を確かめます |
| ポートが使用中 | 既定の 8765 が使用中なら、次の番号で待ち受けます。固定したいときは `--port N` を指定します |
| 画面の内容が古い | データ層のファイルを更新すると、数秒以内に自動で読み直します。ブラウザーを再読み込みしても変わらない場合は、Studio を起動し直します |

そのほかは [Studio のトラブルシューティング](studio/04-troubleshooting.md) を見てください。

## 7.7 Windows 固有の問題

| 症状 | 対処 |
|---|---|
| `python` で Microsoft Store が開く | 実体の Python をインストールし、「アプリ実行エイリアス」の python を無効にします |
| 日本語が文字化けする | スクリプトは UTF-8 で出力します。PowerShell で `$OutputEncoding = [Console]::OutputEncoding = [Text.Encoding]::UTF8` を設定します |
| `verify.ps1` を実行できない | `powershell -ExecutionPolicy Bypass -File scripts/verify.ps1` を使うか、`python scripts/verify.py` を直接実行します |

## 7.8 ログの場所

| 見たいもの | 場所 |
|---|---|
| verify・テストのログの全文 | `work/logs/` |
| rdfix の排他と、元に戻せなかったファイル | `work/.ebak/rdfix.lock`、`work/.ebak/rdfix-undo-*/` |
| 監査の結果 | `work/audit/<日時>/report.md`（各回は `run<n>.md`） |
| CI の結果 | GitHub の Actions 画面（ebak-verify） |
