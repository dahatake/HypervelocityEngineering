**日本語** | [English](01-first-steps.en.md)

# S1 はじめかた

## 利用開始前の前提条件

次を満たすと EABK Studio を利用できます。確認済みの事項と、現時点で根拠資料から確認できない事項を分けて示します。

| 項目 | 前提条件 | 根拠・確認状況 |
|---|---|---|
| Python | Python 3.9 以上が必要です。 | 確認済み: [`README.md`](../../EABK-Studio/README.md) |
| 追加インストール | 追加インストール不要です。3D 表示用の three.js は同梱されています。 | 確認済み: [`README.md`](../../EABK-Studio/README.md) |
| 起動スクリプト | Windows では `start.ps1`、macOS/Linux では `start.sh` を利用できます。各 OS の版別の動作確認範囲は未確認です。 | 確認済み: [`start.ps1`](../../EABK-Studio/start.ps1)、[`start.sh`](../../EABK-Studio/start.sh) |
| ブラウザー | ローカル URL を開くブラウザーが必要です。対応するブラウザー名・版は未確認です。 | 確認済み: 起動時にブラウザーを開く仕様。対応範囲は未確認。 |
| 対象リポジトリ | EABK の管理データがあるリポジトリ（`docs/requirements-definition.md` または `docs/catalog.md` が見つかる場所）か、EABK のない git リポジトリ（コードのモード。下の「EABK なしで Studio を使う」）を指定します。 | 確認済み: [`README.md`](../../EABK-Studio/README.md) |
| ネットワーク | インターネット接続は不要です。Studio は `127.0.0.1` だけで待ち受け、既定ポートは `8765` です。 | 確認済み: [`README.md`](../../EABK-Studio/README.md) |
| 権限・ネットワーク設定 | 管理者権限、ファイアウォール／プロキシの設定、ローカルポート利用許可が必要かどうかは未確認です。必要になった場合は、組織の端末・ネットワーク管理者に確認してください。 | 未確認 |

## 起動

対象リポジトリのフォルダーで、ターミナルを開いて次を実行します。

```powershell
python EABK-Studio/studio.py
```

別の場所から起動するときは、対象を指定します。

```powershell
python EABK-Studio/studio.py --repo C:\path\to\your-repo
```

役割に合った画面から始めるときは `--role` を付けます（`pm` = ダッシュボード、`architect` = 2D マップ、`swe` = 表）。起動前にデータ層が見つかるかだけを確認するときは `--check` です。

```powershell
python EABK-Studio/studio.py --role architect
python EABK-Studio/studio.py --check
```

ブラウザーが開き、`http://127.0.0.1:8765/` を表示します（使用中なら次の番号。ターミナルに出る URL を見てください）。止めるときはターミナルで `Ctrl+C` です。

Windows は `.\EABK-Studio\start.ps1 <リポジトリ>`、macOS / Linux は `./EABK-Studio/start.sh <リポジトリ>` でも起動できます。オプションは、PowerShell では `-Role pm`・`-Check`・`-NoOpen`、シェルでは `./EABK-Studio/start.sh . 8765 --role pm` のように渡せます。

役割別の進め方は [05-product-manager.md](05-product-manager.md)・[06-architect.md](06-architect.md)・[07-software-engineer.md](07-software-engineer.md) にあります。

## 最初の 10 分

1. **ダッシュボード**を見ます。要求の数、承認済みの割合、実装が登録された割合、未回答の質問、BLOCKED（止まっている要求）が分かります。
2. 「目的ごとの実装進捗」の棒をクリックします。その目的に属する要求が、地図で強調されます。
3. **2D マップ**で、ホイールを回して拡大・縮小し、ドラッグで動かします。点にポイントすると、直接つながる項目が光ります。
4. 点をクリックします。右に詳細（要求本文・受入基準・実装ファイル・テスト）が出ます。`Esc` で解除します。
5. 画面上部の検索欄（`/` キーで移動）に、気になる言葉（例: 「ログイン」）を入れて、結果を選びます。図の中で関連が強調されます。
6. 右上の `JA | EN` を押して、言語が切り替わることを確かめます。

## 別のリポジトリを見る

画面右上のリポジトリ名を押し、フォルダーのパスを入力します。起動し直す必要はありません。データ層があるリポジトリと、コードのモードで見られる git リポジトリに切り替えられます。どちらでもないフォルダー（空のフォルダー、git でないフォルダー）は、メッセージが出て切り替わりません。

## EABK なしで Studio を使う（コードのモード）

EABK を入れていない git リポジトリも見られます（FR-1086）。HVE（この toolkit）を clone したフォルダーから、対象のリポジトリのルートを指定します。

```powershell
python EABK-Studio/studio.py --repo C:\path\to\any-git-repo --check
python EABK-Studio/studio.py --repo C:\path\to\any-git-repo
```

`--check` は `mode: code (...) requirement-docs=… requirements=… linked-to-code=… code-files=… test-files=… components=…` の行を出し、exit 0 で終わります。

- データ層があるリポジトリでは、従来どおりデータ層を読みます。
- データ層がないときは、読み取りだけで次を導出します: Markdown の表の先頭の列と見出しにある要求 ID（`FR-…`・`NFR-…`。`docs/PRD.md` や、名前に prd・requirement・要求・spec を含むファイルを先に読みます）、その ID を書いたコードとテストのファイル（カタログの行の実装ファイル・テスト）、コンポーネント（共通部品）にまとめたソースのファイル。
- すべての画面（ダッシュボード・マップ・図式・ソース対応・表）が動きます。台帳・受入基準は空です。
- 対象は git リポジトリのルートだけです（ただのフォルダーは走査しません）。空のフォルダーや git でないフォルダーは「no EABK data layer … and nothing to show in code mode」と出て exit 1 です。
- `--repo` を省略したときは、現在のフォルダー（データ層があるか、コードのモードで見られる git リポジトリのとき）、それ以外は Studio 自身のリポジトリを開きます。
- 例: `C:\GitHub\VideoCreator` では `docs/PRD.md` から 103 件の要求、そのうち 56 件がコード・テストにつながり、コードのファイル 78・コンポーネント 6 を表示しました。
