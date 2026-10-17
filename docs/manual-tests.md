# 手順で確かめる受入基準

コマンドで自動判定しにくく、手順で確かめる受入基準の一覧です。

## NFR-COMPAT-002 AC-090 性能改善による挙動の不変

1. 改善前の commit と改善後の commit で、同一のリポジトリ状態に対して `python scripts/verify.py --docs-only` と `python scripts/rdcheck.py` を実行し、標準出力・標準エラー出力・終了コードを記録する。
2. 2 つの記録が一致することを確認する。
3. `python -m pytest -q tests/toolkit` が全件 pass することを確認する（`tests/toolkit/test_git_perf.py` は同一状態での出力の再現性を自動で確かめる）。

## FR-1054 AC-293 RPG 風の独自性（既存の著作物を複製していない）

1. `docs/rpg-originality.md` の「確認項目」を、Studio を `python EABK-Studio/studio.py --repo <リポジトリ>` で起動し、マップを RPG 風にして、音を入にした状態で 1 つずつ確かめる（野外・街・城の 3 場面の音楽、5 種以上の効果音、3 種のキャラクターを見聞きする）。
2. ブラウザーの開発者ツールのネットワーク欄で、同じ配信元以外への要求と、画像・音声・フォントのファイルの取得がないことを確かめる。
3. すべての確認項目が「はい」であることを記録する。
