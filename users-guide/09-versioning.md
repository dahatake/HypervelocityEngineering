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
5. 配布物（ファイル）を追加・改名・削除した場合は、`tools/install.py` の `MANAGED`・`TEMPLATES`・`OBSOLETE` と、この `users-guide/` を合わせて直します。`users-guide/` の全ファイルは `MANAGED` に列挙し、導入先では `EABK-docs/` に保存されます（導入先の `users-guide/` は編集しません）。
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

1. 作業ツリーをきれいにします（未 commit の変更を commit か退避します）。0.5.x から 0.6.0 に上げるときは、先に 9.4 を読みます。
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
   | `REMOVE` | 新しい版では配布しなくなったファイルを、変更していなかったので削除しました |
   | `KEEP-LOCAL` | ローカルで変更したファイルは更新していません。差分を確認し、上書きしてよければ `--force` を付けて再実行します（`*.ebak-backup-<日時>` が残ります） |
   | `PRUNE` | `scripts/ebak.config.json` から、新しい版で使わなくなったキーを削除しました（0.6.0 では `gates`・`limits`・`credits`・`worktree_share` と、旧既定の検証コマンド `toolkit-unit`） |

   管理データ（`docs/` と台帳）と `scripts/ebak.config.json` の既存の値は変更されません。`ebak.config.json` には、新しいキーだけが追加され、使わなくなったキーは削除されます（`PRUNE`）。
5. 検証します。インストーラが最後に `python scripts/rdfix.py --full --apply` を 1 回実行します（`--no-repair` で計画だけ、`--skip-verify` で省略）。続けて全体の検証も通します。
   ```bash
   python scripts/verify.py
   ```
6. 差分を確認して commit します。
   ```bash
   git add -A && git commit -m "Update Enterprise App Build Kit to 0.2.0"
   ```
7. CI で版のずれを検出するには、`--check` を使います。

## 9.4 0.5.x から 0.6.0（EABK Lite）へ移行する

0.6.0 は互換性のない変更です。オーケストレーション（conductor と作業役、worktree の run、`/build`、役割のゲート）をやめ、規則（AGENTS.md）・データ層・決定的な検査（`verify.py` と CI）・節目の監査（rd-auditor）・EABK Studio だけを残しました。管理データ（要求定義書・カタログ・台帳・ID 台帳）の書式は変わりません。

| 0.5.x で使っていたもの | 0.6.0 での代わり |
|---|---|
| `/build` と conductor | いつもの Copilot（既定のエージェント）にふだんどおり依頼します。AGENTS.md の規則に従い、要求・カタログ・テスト・コードが同じ変更で更新されます |
| `<run_options>`（`max_hours`・`parallel_workers`・`scope` など） | 不要です。制約を伝えたいときは依頼文に書きます |
| `approval_policy` の包括承認 | チャットで承認します（例: `FR-031: 承認`） |
| rd-author だけが要求定義書を編集する | 誰が編集してもかまいません。ID は `next-id.py` でだけ採番し、台帳は `ledger.py` でだけ更新します |
| `run-state.py`・`integrate.py`・`kpi.py`・`watch.py`・`clean-work.py` | 代わりはありません。進捗と統合は git とプルリクエスト、検査は CI（`ebak-verify`・`ebak-data-layer`）に任せます |
| hook（`quality-gates.json`・`prompt-prefix.json`）と定型文の自動付与 | ありません。同じ規則は `verify.py` と CI が検査します。毎回伝えたい前提は、自分の Copilot の instructions に書きます |
| `docs/run-history.md` | 残っていれば読み取り専用の記録です（EABK Studio が表示します）。新しい行は追記されません |

手順:

1. 0.5.x の run が動いていないことを確かめ、作業ツリーをきれいにします。
2. 9.3 の手順でインストールコマンドを再実行します。変更していない旧ファイル（conductor・rd-author・test-designer・implementer・reviewer の agent、build・build-template・implement-fr・system-test-increment・dedupe の skill、hook のファイル（`.github/hooks/quality-gates.json`・`.github/hooks/prompt-prefix.json`・`scripts/hooks/gate.py`）、`run-state.py`・`integrate.py`・`next-impl.py`・`build-request.py`・`watch.py`・`kpi.py`・`clean-work.py`・`select-tests.py`）は `REMOVE`、変更したものは `KEEP-LOCAL` で残ります（不要なら `--force` で削除・上書き）。設定の旧キー（`gates`・`limits`・`credits`・`worktree_share`・`prompt_prefix`）は `PRUNE` で消えます。要求定義書・台帳・カタログは変わりません。`.github/ebak-prompt-prefix.md` は残りますが、もう読みません。
   - `WARN-HOOK  <パス>` が出たら、ローカルで変更した hook のファイルが残っています。そのファイルは削除された `gate.py` を呼び、hook がエラーになると Copilot がすべてのツールを拒否します。ファイルを削除してから Copilot のセッションを開き直します。
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

0.1.0 に版を整理する前の記録（`toolkit_version: 1.2.0` や `1.3.0`、`docs/run-history.md` の過去の行など）は、当時の表記のまま残しています。導入済みの環境の `.github/ebak-toolkit.json` に `1.3.0` と書かれている場合も、9.3 の手順で更新すると 0.1.0 以降の版に置き換わります。
