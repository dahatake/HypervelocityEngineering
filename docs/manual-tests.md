**日本語** | [English](manual-tests.en.md)

# 手順で確かめる受入基準

コマンドで自動判定しにくく、手順で確かめる受入基準の一覧です。

## NFR-COMPAT-002 AC-090 性能改善による挙動の不変

1. 改善前の commit と改善後の commit で、同一のリポジトリ状態に対して `python scripts/verify.py --docs-only` と `python scripts/rdcheck.py` を実行し、標準出力・標準エラー出力・終了コードを記録する。
2. 2 つの記録が一致することを確認する。
3. `python -m pytest -q tests/toolkit` が全件 pass することを確認する（`tests/toolkit/test_git_perf.py` は同一状態での出力の再現性を自動で確かめる）。

## FR-1087 AC-475 AC-476 AC-478 全版の導入と削除（toolkit の保守。版の更新の前）

自動テスト（`tests/toolkit/test_uninstall.py`）は最古の版と現在の版だけを実際に導入して確かめます。すべての版は、次の手順で確かめます（toolkit のリポジトリの完全な clone で行います）。

1. `python tools/build-uninstall-catalog.py --check` が exit 0 であることを確認する（カタログが git の履歴と一致する）。
2. `python tools/verify-uninstall-matrix.py` を実行する。代表的な版のそれぞれを、その版の `tools/install.py` で、利用者のファイルを commit したリポジトリに導入し、manifest のまま・manifest を消して・現在の版で更新してから、の 3 通りで `tools/uninstall.py --purge --runs` を実行する。すべてが `OK` で exit 0 であることを確認する。
3. `python tools/verify-uninstall-matrix.py --all` を実行する。すべての版（merge で入った版を含む）を manifest を消して導入し、同じように削除する。すべてが `OK` で exit 0 であることを確認する。
4. 判定は、削除後の `git status --porcelain --ignored --untracked-files=all` が空であること（導入前の commit とバイト単位で同じ）。失敗の詳細は `work/uninstall-matrix/log-<commit>-<variant>.txt` にある。
5. 他のリポジトリで: `tools/uninstall.ps1 -DryRun`（または `tools/uninstall.sh --dry-run`）を、toolkit の clone の外のリポジトリで、`main` から 2 ファイルをダウンロードする形で実行し、一覧が表示されて何も変わらないことを確認する。
