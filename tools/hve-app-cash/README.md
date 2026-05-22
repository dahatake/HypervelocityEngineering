# clear-python-catch

Python バイトコードキャッシュ（`__pycache__` / `*.pyc` / `*.pyo`）を再帰的に削除するスクリプト群。GUI にコード変更が反映されない場合の最初のリセット手段として使用する。

## ファイル

| OS | ファイル |
|---|---|
| Windows (PowerShell) | `clear-python-catch.ps1` |
| Windows (cmd) | `clear-python-catch.cmd` |
| macOS / Linux | `clear-python-catch.sh` |

## 使い方

### Windows

```powershell
pwsh -File tools\hve-app-cash\clear-python-catch.ps1
pwsh -File tools\hve-app-cash\clear-python-catch.ps1 -DryRun     # 削除候補のみ表示
```

または cmd から:

```cmd
tools\hve-app-cash\clear-python-catch.cmd
```

### macOS / Linux

```bash
bash tools/hve-app-cash/clear-python-catch.sh
bash tools/hve-app-cash/clear-python-catch.sh --dry-run
```

実行権限を付ける場合:

```bash
chmod +x tools/hve-app-cash/clear-python-catch.sh
./tools/hve-app-cash/clear-python-catch.sh
```

## 動作

- 既定の対象パスはリポジトリルート（スクリプトの 2 階層上）。
- 第 1 引数（または `-Path`）で対象ディレクトリを変更可能。
- `--dry-run` / `-DryRun` で削除せず候補のみ表示。

## 注意

- アプリ内部キャッシュ（モデル一覧キャッシュ・Pricing キャッシュ・QtWebEngine キャッシュ）は対象外。これらは設定画面または該当パスを別途削除すること。
