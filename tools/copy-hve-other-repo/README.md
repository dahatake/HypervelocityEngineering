# HVE application を別フォルダーへコピーする

このツールは、現在のリポジトリから **HVE application の保守・実行に必要なファイルだけ**を抽出し、指定した別フォルダーへ置き換えコピーします。

## 最重要の動作

- コピー先直下の `.git` は、ディレクトリでも Git worktree 用ファイルでも**削除・上書きしません**。
- コピー先に既にある `.git` 以外のファイル、隠しファイル、フォルダー、リンクは**すべて削除**します。
- 既存ファイルを残したまま上書きする同期処理ではありません。削除が完了したことを確認してからコピーを始めます。
- source と destination が同じ、包含関係にある、destination がファイルシステムルートまたはホームディレクトリである場合は、削除前に停止します。
- コピー対象の全ファイルを一時フォルダーへ staging できた場合だけ、コピー先の削除を始めます。
- コピー元は現在の Git worktree です。追跡済みファイルの未 commit 変更と、`.gitignore` 対象外の未追跡ファイルを反映し、削除済みファイルと ignore 対象はコピーしません。

> 実行前に、コピー先の必要な変更を commit、push、または別媒体へバックアップしてください。`.git` は保持されますが、未追跡ファイルを含む作業ツリーは消去されます。

## コピーされる範囲

主なコピー対象は次のとおりです。

- `hve/`、`mdq/`、`cq/`
- `hve-dev/`、`template/`
- HVE 用 `.github/` 資産（prompts、skills、I/O contracts、scripts、Issue templates、HVE workflows など）
- `tools/` 直下の HVE 用スクリプトと `tools/io-contracts-README.md`、`tools/skills/` の HVE 関連キット、`tools/runner/`、`tools/for-other-repo/`
- `users-guide/`
- `tests/prompt-version/`、`tests/[cli]SystemTest - Full.txt`、`tests/[gui]SystemTest - Full.txt`（コピーされる `hve/tests/` が実在を検証するシステムテスト手順書）
- `pyproject.toml`、`hve.cmd`、`hve.sh`、`mdq.toml`、`cq.toml`
- `.gitignore`、`.gitattributes`、`README.md`、`CHANGELOG.md`、`LICENSE`
- `.vscode/` の HVE 開発設定

HVE と生成アプリの境界判定には `.github/scripts/hve_scope.py` を使用します。次の生成アプリ領域などはコピーしません。

- `src/`、`docs/`、`docs-generated/`
- `knowledge/`、`qa/`、`docs-original/`、`sample/`
- `work/`、`tests/run/`、`hve.egg-info/`
- `local-llm-dev/`、`tools/hve-app-cash/`
- `.github/workflows/deploy-*`、`.github/workflows/azure-static-web-apps-*`、`.github/workflows/app<数字>*`
- 生成アプリ用 `package.json`、Jest、Babel、Playwright 設定
- このコピーツール自身の `tools/copy-hve-other-repo/`

`.gitignore` 対象のため、個人設定 `hve/.settings.txt` とローカル状態 `.hve/`、`.mdq/`、`.cq/`、`.venv/` も引き継がれません。コピー先では `hve/setup-hve.*` を実行し、GUI 設定を入力し直してください。

## 前提条件

### Windows

- PowerShell 7 以上（`pwsh.exe`）
- Python 3.11 以上
- Git

リポジトリの `.venv\Scripts\python.exe` があれば自動的に使用し、なければ PATH 上の `python` を使用します。

### macOS

- Bash
- Python 3.11 以上
- Git

リポジトリの `.venv/bin/python` があれば自動的に使用し、なければ PATH 上の `python3` を使用します。任意の Python を使う場合は環境変数 `PYTHON` に実行ファイルを指定できます。

## Windows チュートリアル

以下はリポジトリルートから実行します。

### 1. 削除対象を確認する

```powershell
pwsh.exe -NoLogo -NoProfile -File .\tools\copy-hve-other-repo\copy-hve.ps1 -Destination "C:\GitHub\HveStandalone" -DryRun
```

`-DryRun` は、コピーするファイル数と削除予定の直下エントリ数を表示するだけで、コピー先を変更しません。

### 2. コピーを実行する

```powershell
pwsh.exe -NoLogo -NoProfile -File .\tools\copy-hve-other-repo\copy-hve.ps1 -Destination "C:\GitHub\HveStandalone"
```

表示されたパスを確認し、続行する場合は `DELETE` と入力します。自動実行で確認を省略する場合だけ `-Yes` を指定します。

```powershell
pwsh.exe -NoLogo -NoProfile -File .\tools\copy-hve-other-repo\copy-hve.ps1 -Destination "C:\GitHub\HveStandalone" -Yes
```

### 3. コピー先を確認する

```powershell
git -C "C:\GitHub\HveStandalone" status --short
Test-Path -LiteralPath "C:\GitHub\HveStandalone\.git"
```

### 4. HVE をセットアップする

```powershell
Set-Location "C:\GitHub\HveStandalone"
pwsh.exe -NoLogo -NoProfile -File .\hve\setup-hve.ps1
.\hve.cmd --help
```

## macOS チュートリアル

以下はリポジトリルートから実行します。

### 1. 削除対象を確認する

```bash
bash tools/copy-hve-other-repo/copy-hve.sh "/Users/your-name/GitHub/hve-standalone" --dry-run
```

### 2. コピーを実行する

```bash
bash tools/copy-hve-other-repo/copy-hve.sh "/Users/your-name/GitHub/hve-standalone"
```

表示されたパスを確認し、続行する場合は `DELETE` と入力します。自動実行で確認を省略する場合だけ `--yes` を指定します。

```bash
bash tools/copy-hve-other-repo/copy-hve.sh "/Users/your-name/GitHub/hve-standalone" --yes
```

### 3. コピー先を確認する

```bash
git -C "/Users/your-name/GitHub/hve-standalone" status --short
test -e "/Users/your-name/GitHub/hve-standalone/.git"
```

### 4. HVE をセットアップする

```bash
cd "/Users/your-name/GitHub/hve-standalone"
bash hve/setup-hve.sh
./hve.sh --help
```

## オプション

| 共通実装 | Windows | 説明 |
|---|---|---|
| `--dry-run` | `-DryRun` | 件数確認だけを行い、削除・コピーしない |
| `--yes` | `-Yes` | `DELETE` の対話確認を省略する |
| — | `-Python <path>` | 使用する Python 実行ファイルを明示する |

macOS で Python を明示する例:

```bash
PYTHON="/opt/homebrew/bin/python3.14" bash tools/copy-hve-other-repo/copy-hve.sh "/Users/your-name/GitHub/hve-standalone" --dry-run
```

## 失敗時の扱い

- source の必須ファイル不足、Git 列挙失敗、危険なパス、staging 失敗では、コピー先を削除しません。
- コピー先の削除に 1 件でも失敗すると、新しい HVE ファイルのコピーを開始しません。
- staging 後の最終コピー中に OS エラーが起きた場合、`.git` は保持されますが、HVE ファイルは途中までの状態になり得ます。原因を解消して同じコマンドを再実行してください。
- コピー先に `.git` がない場合も実行できます。その場合は通常の空フォルダーとして作成または置換されます。

## テスト

```powershell
.\.venv\Scripts\python.exe -m pytest tools/copy-hve-other-repo/test_copy_hve.py -q
```

macOS では次を使用します。

```bash
.venv/bin/python -m pytest tools/copy-hve-other-repo/test_copy_hve.py -q
```