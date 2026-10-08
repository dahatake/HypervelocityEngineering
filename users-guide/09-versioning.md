# バージョンアップの手順

Enterprise App Build Kit の版の付け方と、版を上げる手順（配布元の保守者向け）、導入済みリポジトリを新しい版に更新する手順（利用者向け）です。

## 9.1 版の規則

- 版は [Semantic Versioning](https://semver.org/lang/ja/)（`MAJOR.MINOR.PATCH`）に従います。現在の版は **0.2.0** です。
- 版の正本は `scripts/ebaklib.py` の `TOOLKIT_VERSION` です。インストーラ（`tools/install.py`）、`bench/bench.py`、`scripts/run-state.py` の記録は、すべてここから読みます。ほかの場所に版を書き写しません。
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
5. 配布物（ファイル）を追加・改名・削除した場合は、`tools/install.py` の `MANAGED`・`TEMPLATES`・`OBSOLETE` と、この `users-guide/` を合わせて直します。
6. 版を確認し、commit してタグを付けます。
   ```bash
   python tools/install.py --version     # 例: 0.2.0
   git add -A && git commit -m "Release 0.2.0"
   git tag v0.2.0
   git push origin main --tags
   ```
7. 別の空のリポジトリで、`EBAK_REF=v0.2.0` を指定して導入できることを確認します（9.3 の手順 2〜3 と同じです）。

## 9.3 導入済みのリポジトリを更新する（利用者向け）

導入済みのバージョンは `.github/ebak-toolkit.json` の `version` に記録されています。

1. 作業ツリーをきれいにします（未 commit の変更を commit か退避します）。run が `active` のときは、終わるまで待ちます。
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

   管理データ（`docs/` と台帳）と `scripts/ebak.config.json` の既存の値は変更されません。`ebak.config.json` には、新しいキーだけが追加されます。
5. 検証します。インストーラが最後に `python scripts/verify.py --docs-only` を実行します。続けて全体の検証も通します。
   ```bash
   python scripts/verify.py
   ```
6. 差分を確認して commit します。
   ```bash
   git add -A && git commit -m "Update Enterprise App Build Kit to 0.2.0"
   ```
7. CI で版のずれを検出するには、`--check` を使います。

## 9.4 元に戻す

更新を戻すときは、更新の commit を `git revert` します。特定の版に戻したいときは、`EBAK_REF=v0.1.0` と `--force` を付けて、インストールコマンドを再実行します。インストーラは版が異なれば更新と判断するので、古い版を指定した場合も同じ手順で置き換わります。

## 9.5 版の表記についての注意

0.1.0 に版を整理する前の記録（`bench/results/` の `toolkit_version: 1.2.0` や `1.3.0`、`docs/run-history.md` の過去の行など）は、当時の表記のまま残しています。導入済みの環境の `.github/ebak-toolkit.json` に `1.3.0` と書かれている場合も、9.3 の手順で更新すると 0.1.0 以降の版に置き換わります。
