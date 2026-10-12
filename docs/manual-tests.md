# 手順で確かめる受入基準

コマンドで自動判定しにくく、手順で確かめる受入基準の一覧です。

## NFR-COMPAT-002 AC-090 性能改善による挙動の不変

1. 改善前の commit と改善後の commit で、同一のリポジトリ状態に対して `python scripts/verify.py --docs-only` と `python scripts/rdcheck.py` を実行し、標準出力・標準エラー出力・終了コードを記録する。
2. 2 つの記録が一致することを確認する。
3. `python -m pytest -q tests/toolkit` が全件 pass することを確認する（`tests/toolkit/test_git_perf.py` は同一状態での出力の再現性を自動で確かめる）。
