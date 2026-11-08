**日本語** | [English](09-versioning.en.md)

# バージョンアップの手順

Enterprise App Build Kit の版の付け方と、版を上げる手順（配布元の保守者向け）、導入済みリポジトリを新しい版に更新する手順（利用者向け）です。

## 9.1 版の規則

- 版は [Semantic Versioning](https://semver.org/lang/ja/)（`MAJOR.MINOR.PATCH`）に従います。現在の版は **0.6.0**（EABK Lite）です。
- 版の正本は `scripts/ebaklib.py` の `TOOLKIT_VERSION` です。インストーラ（`tools/install.py`）と `.github/ebak-toolkit.json` の記録は、すべてここから読みます。ほかの場所に版を書き写しません。
- 変更履歴は、リポジトリ直下の [CHANGELOG.md](../CHANGELOG.md) に書きます。
- 1.0.0 になるまでは、MINOR の更新で互換性のない変更が入ることがあります。

| 上げる桁 | 使う場面 |
|---|---|
| MAJOR | 互換性のない変更（管理データの書式の変更、スクリプトのオプションの削除など） |
| MINOR | 後方互換のある機能の追加（エージェント・skill・検査項目・オプションの追加など） |
| PATCH | 後方互換のある不具合の修正、文章の修正 |

## 9.2 版を上げる（配布元の保守者向け）

1. 変更を `main` に取り込み、`CHANGELOG.md` の `## [Unreleased]` の下に、変更内容を書きます。
2. toolkit のテストを実行し、すべて通ることを確認します。
   ```bash
   python -m pytest tests/toolkit -q
   ```
3. 版を上げます。`major`・`minor`・`patch` か、`X.Y.Z` の直接指定を使います。
   ```bash
   python tools/bump-version.py minor     # 0.1.0 -> 0.2.0
   ```
   `TOOLKIT_VERSION` が書き換わり、`CHANGELOG.md` の `[Unreleased]` の下に新しい版の見出しが入ります。引数なしで実行すると、現在の版を表示するだけです。
4. `CHANGELOG.md` で、`[Unreleased]` に書いた内容を新しい版の見出しの下へ移します。
5. 配布物（ファイル）を追加・改名・削除した場合は、`tools/install.py` の `MANAGED`・`TEMPLATES` と、この `users-guide/` を合わせて直します。`users-guide/` の全ファイルは `MANAGED` に列挙し、導入先では `EABK-docs/` に保存されます（導入先の `users-guide/` は編集しません）。
6. 版を確認し、commit してタグを付けます。
   ```bash
   python tools/install.py --version     # 例: 0.4.0
   git add -A && git commit -m "Release 0.2.0"
   git tag v0.2.0
   git push origin main --tags
   ```
7. 別の空のリポジトリで、`EBAK_REF=v0.2.0` を指定して導入できることを確認します（9.3 の手順 2〜3 と同じです）。

## 9.3 導入済みのリポジトリを更新する（利用者向け）

導入済みのバージョンは `.github/ebak-toolkit.json` の `version` に記録されています。

1. 作業ツリーをきれいにします（未 commit の変更を commit か退避します）。旧版（0.5.x など）から上げるときは、9.4 のクリーンインストールを使います。
2. 更新が必要かを確認します。必要なら exit 1 になります。
   ```bash
   curl -fsSL https://raw.githubusercontent.com/dahatake/HypervelocityEngineering/main/tools/install.sh | bash -s -- --check
   ```
   何が変わるかを見たいときは `--dry-run` を使います（PowerShell は `-Check`・`-DryRun`）。
3. 更新します。インストールコマンドをもう一度実行するだけです。特定の版にしたいときは `EBAK_REF=v0.2.0` を付けます。
   ```bash
   EBAK_REF=v0.2.0 curl -fsSL https://raw.githubusercontent.com/dahatake/HypervelocityEngineering/main/tools/install.sh | bash
   ```
   PowerShell は `$env:EBAK_REF = "v0.2.0"` を設定してから、README のコマンドを実行します。
4. 結果の表示を確認します。

   | 表示 | 意味と対応 |
   |---|---|
   | `UPDATE` | 新しい版に更新しました |
   | `KEEP-LOCAL` | ローカルで変更したファイルは更新していません。差分を確認し、上書きしてよければ `--force` を付けて再実行します（`*.ebak-backup-<日時>` が残ります） |
   | `注意: この版が配布しないファイルが N 件残っています` | 旧版が入れたファイルです。更新では削除しません。9.4 の `--clean` で入れ直します |

   管理データ（`docs/` と台帳）と `scripts/ebak.config.json` の既存の値は変更されません。`ebak.config.json` には新しいキーだけが追加されます（使わなくなったキーは消しません）。
5. 検証します。インストーラが最後に `python scripts/rdfix.py --full --apply` を 1 回実行します（`--no-repair` で計画だけ、`--skip-verify` で省略）。続けて全体の検証も通します。
   ```bash
   python scripts/verify.py
   ```
6. 差分を確認して commit します。
   ```bash
   git add -A && git commit -m "Update Enterprise App Build Kit to 0.2.0"
   ```
7. CI で版のずれを検出するには、`--check` を使います。

## 9.4 旧版から更新する（クリーンインストール）

インストーラは旧版からの移行の処理（版ごとの削除リストや設定の書き換え）を持ちません。旧版から更新するときは `--clean` でクリーンインストールします。マニフェストに記録された「toolkit が入れたファイル」をすべて消してから入れ直すので、どの版からでも同じ手順です。

0.6.0 は 0.5.x と互換性のない変更です。オーケストレーション（conductor と作業役、worktree の run、`/build`、役割のゲート）をやめ、規則（AGENTS.md）・データ層・決定的な検査（`verify.py` と CI）・節目の監査（rd-auditor）・EABK Studio だけを残しました。管理データ（要求定義書・カタログ・台帳・ID 台帳）の書式は変わりません。

| 0.5.x で使っていたもの | 0.6.0 での代わり |
|---|---|
| `/build` と conductor | いつもの Copilot（既定のエージェント）にふだんどおり依頼します。AGENTS.md の規則に従い、要求・カタログ・テスト・コードが同じ変更で更新されます |
| `<run_options>`（`max_hours`・`parallel_workers`・`scope` など） | 不要です。制約を伝えたいときは依頼文に書きます |
| `approval_policy` の包括承認 | チャットで承認します（例: `FR-031: 承認`） |
| rd-author だけが要求定義書を編集する | 誰が編集してもかまいません。ID は `next-id.py` でだけ採番し、台帳は `ledger.py` でだけ更新します |
| `run-state.py`・`integrate.py`・`kpi.py`・`watch.py`・`clean-work.py` | 代わりはありません。進捗と統合は git とプルリクエスト、検査は CI（`ebak-verify`）に任せます |
| hook（`quality-gates.json`・`prompt-prefix.json`）と定型文の自動付与 | ありません。同じ規則は `verify.py` と CI が検査します。毎回伝えたい前提は、自分の Copilot の instructions に書きます |
| `.github/workflows/ebak-data-layer.yml`（PR・push・毎週の自動修復の commit と Issue。contents・pull-requests・issues の write の権限） | 撤去しました（FR-1017・FR-1018・FR-1019、NFR-SEC-004、NFR-OPS-006 は廃止）。`--clean` で削除されます。CI は検査だけの `ebak-verify`（読み取りの権限）です。修復は手元で `python scripts/rdfix.py --full --apply` を実行し、同じ変更に含めます。読むだけの CI には書き込みの権限が要らず、bot が誰かの PR のブランチへ修復を push すると、ほかの人・PC のブランチが食い違うためです |
| `rdcheck.py check`・`verify.py` の `--run`・`--strict`・`--strict-ledger`・`--no-strict-ledger`、CHK-21 | 撤去しました（付けると引数のエラーで exit 2）。つまみは検査プロファイル（`checks.profile`・`--profile lite`／`full`）だけです。`--strict` で error になっていた CHK-00・09・13 と、`--strict-ledger` の CHK-10・11 は WARN で、`--profile full --show-warnings` で見られます。要約行から `run=` を外しました |
| `rdfix.py --apply` の作業役のブランチ（`work/<run-id>/<item>`）での拒否 | 撤去しました。exit 2 は、排他の待ち時間切れ・すべての取り消し・内部エラーだけです |
| `work.retention_days`（`/work` の 14 日の清掃） | 撤去しました（`--clean` で設定から消えます）。`/work` は不要になったら手で削除します |
| 既定の `verify.commands`（`toolkit-unit`・`studio-ui` = `python -m pytest -q EABK-Studio/tests`）と、導入先の `EABK-Studio/tests/` | `--clean` で消えます。導入先には Studio のテストを入れません。新しい導入の `verify.commands` は空（`[]`）なので、自分のビルド・テストのコマンドを登録します |
| `ledger.py run` の結果を run のフォルダーに書く | 結果は `work/system-test/results.json` に書きます（`--results` で変更できます） |

手順:

1. 0.5.x の run が動いていないことを確かめ、作業ツリーをきれいにします（未 commit の変更があると `--clean` は実行しません）。
2. 削除する一覧（`CLEAN`）を確かめてから、クリーンインストールします。PowerShell では `-Clean` です。
   ```bash
   python tools/install.py --target . --clean --dry-run
   python tools/install.py --target . --clean
   ```
   toolkit が入れたファイル（conductor などの agent、build などの skill、hook のファイル `.github/hooks/*.json`・`scripts/hooks/gate.py`、撤去したスクリプト、`.github/workflows/ebak-data-layer.yml`。変更したものも）・`.ebak-backup-*`・設定・ブロック・`.gitignore`/`.gitattributes` に追記した行・マニフェストを削除し、この版を入れ直します。管理データ・`/work`・アプリのコードとテストは残ります。設定は既定に戻るので、以前の値は `git diff scripts/ebak.config.json` で確かめて戻します。2 回続けて実行しても、2 回目は何も変わりません。
   - 旧版のデータ層のファイル（0.5.x の `docs/run-history.md`）と `.github/ebak-prompt-prefix.md` は残りますが、もう読みません。不要なら手で削除します。
3. AGENTS.md と `.github/copilot-instructions.md` のブロックが「Enterprise App Build Kit Lite」の規則に置き換わったことを確かめます。
4. 0.5.x の run が残した worktree と `work/*` ブランチは自動では消えません。確認して、不要なら手で消します。
   ```bash
   git worktree list
   git branch --list "work/*"
   git worktree remove <パス>      # 不要な worktree
   git branch -D <ブランチ>        # 不要なブランチ
   ```
5. `python scripts/verify.py` を exit 0 にし、差分を確認して commit します。検査の範囲は既定で `lite` です（`checks.profile`。全項目は `--profile full`）。

## 9.5 元に戻す

更新を戻すときは、更新の commit を `git revert` します。特定の版に戻したいときは、`EBAK_REF=v0.1.0` と `--force` を付けて、インストールコマンドを再実行します。インストーラは版が異なれば更新と判断するので、古い版を指定した場合も同じ手順で置き換わります。

## 9.6 版の表記についての注意

0.1.0 に版を整理する前の記録（`toolkit_version: 1.2.0` や `1.3.0` など）は、当時の表記のまま残しています。導入済みの環境の `.github/ebak-toolkit.json` に `1.3.0` と書かれている場合も、9.3 の手順で更新すると 0.1.0 以降の版に置き換わります。
