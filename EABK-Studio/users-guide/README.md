# EABK Studio ユーザーガイド

EABK Studio は、EABK が管理している「要求・カタログ・試験の記録」（データ層）を、**図・表・検索**で見て回るための、あなたのパソコンだけで動くアプリです。コードを読めなくても、「何を作ると決めたか」「どこまで作ったか」「どの部品・データ・APIがどこにあるか」が分かります。

![EABK Studio のヘッダー](images/header.png)

## あなたの役割から読む

| あなたは | 最初に読む | 起動 | 最初の画面 |
|---|---|---|---|
| Product Manager（何に投資するか決める） | [05-product-manager.md](05-product-manager.md) | `python EABK-Studio/studio.py --role pm` | ダッシュボード |
| Architect（設計の整合・境界を確かめる） | [06-architect.md](06-architect.md) | `python EABK-Studio/studio.py --role architect` | 2D マップ |
| Software Engineer（実装・テストの場所を探す） | [07-software-engineer.md](07-software-engineer.md) | `python EABK-Studio/studio.py --role swe` | 表 |

役割は、画面右上の `Product Manager`・`Architect`・`Software Engineer` のボタンでも、いつでも切り替えられます。

## 読む順

| 読む順 | ファイル | 内容 |
|---|---|---|
| 1 | [01-first-steps.md](01-first-steps.md) | 起動のしかた、最初の 10 分 |
| 2 | [02-screens.md](02-screens.md) | 画面で何が分かるか（実画面つき） |
| 3 | 役割別のガイド（上の表） | 15 分のチュートリアル、おすすめのリンク、判断できること |
| 4 | [03-tasks.md](03-tasks.md) | 「こんなとき、どう見るか」の手順集 |
| 5 | [08-data-reference.md](08-data-reference.md) | どの画面が、どのファイルの何を読んで、どう計算するか |
| 6 | [04-troubleshooting.md](04-troubleshooting.md) | うまく動かないとき（`--check`）・用語集 |

このガイドは対象リポジトリの `EABK-Studio/users-guide/` に、ツール本体と一緒に入ります（`tools/install.py` で EABK を入れると入ります）。技術的な仕様は `EABK-Studio/README.md` にあります。画像は、ツールを作ったリポジトリ自身のデータを読んだ例です（採取条件は [screen-images.json](screen-images.json)、再採取は `capture-screens.py`）。

## 先に知っておくこと

- **通常の閲覧は読むだけです**。例外として、利用者が「整合性保守」で差分を確認して実行した場合だけ、カタログの題名・決定状態を要求正本へ合わせます。失敗時は元の内容へ戻します。
- **外へ送りません**。通信は自分のパソコン内（127.0.0.1）だけです。ソースコードは開きません。
- **自動で最新になります**。データ層のファイルが更新されると、数秒で画面が読み直されます。
- 画面右上の `JA | EN` で、画面の言葉を日本語と英語に切り替えられます（要求の本文などは書かれたままです）。
