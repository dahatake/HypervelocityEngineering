# 2. 導入（インストール・更新・削除）

## 2.1 前提

| 必要なもの | 確かめ方 | 備考 |
|---|---|---|
| git のリポジトリ | `git status` | まだなら `git init -b main` と最初の commit |
| Python 3.9 以上 | `python --version`（macOS/Linux は `python3 --version`） | スクリプトと hook が使います。標準ライブラリだけで動き、追加のパッケージは不要です。Windows では Microsoft Store の `python` スタブではなく、実体の Python を入れます（`winget install Python.Python.3.12`） |
| GitHub Copilot | VS Code（Agents ウィンドウ）または Copilot CLI | 長時間の実行は VS Code の Copilot harness（Agent Host）と Autopilot を想定しています（計画書 A-1） |

## 2.2 単一コマンドで導入する（推奨）

導入したいリポジトリの**ルート**で、次の 1 行を実行します。GitHub から toolkit を一時フォルダーに取得し、`tools/install.py` を実行して、一時フォルダーを削除します。

**Windows（PowerShell）**

```powershell
irm https://raw.githubusercontent.com/dahatake/HypervelocityEngineering/main/tools/install.ps1 | iex
```

オプションを付けるとき:

```powershell
& ([scriptblock]::Create((irm https://raw.githubusercontent.com/dahatake/HypervelocityEngineering/main/tools/install.ps1))) -DryRun
```

**macOS / Linux / WSL / Git Bash**

```bash
curl -fsSL https://raw.githubusercontent.com/dahatake/HypervelocityEngineering/main/tools/install.sh | bash
# オプションを付けるとき
curl -fsSL https://raw.githubusercontent.com/dahatake/HypervelocityEngineering/main/tools/install.sh | bash -s -- --dry-run
```

特定の版（タグ・ブランチ・commit）を使うときは、環境変数 `HVE_REF` を指定します（例: `HVE_REF=v1.0.0`）。フォークを使うときは `HVE_REPO=<owner>/<repo>` を指定します。

**toolkit を clone 済みのとき**

```bash
python tools/install.py --target /path/to/your-repo
```

## 2.3 オプション

| オプション（install.py / install.sh） | PowerShell | 動作 |
|---|---|---|
| `--target <dir>` | `-Target` | 導入先（既定: カレントディレクトリ） |
| `--dry-run` | `-DryRun` | 書き込まずに、行う操作だけを表示します |
| `--check` | `-Check` | 更新が必要かを確かめます（必要なら exit 1。CI で版のずれを検出できます） |
| `--force` | `-Force` | ローカルで変更した toolkit のファイルも上書きします（`*.hve-backup-<日時>` を残します） |
| `--no-ci` | `-NoCi` | `.github/workflows/hve-verify.yml` を入れません |
| `--uninstall` | `-Uninstall` | 変更していない toolkit のファイルを削除します（管理データは残します） |

## 2.4 導入されるもの

| 種類 | ファイル | 再実行時の扱い |
|---|---|---|
| toolkit のファイル | `.github/agents/*.agent.md`（6）、`.github/skills/*/SKILL.md`（4）、`.github/hooks/quality-gates.json`、`.github/prompts/build.prompt.md`、`.github/workflows/hve-verify.yml`、`scripts/*.py`・`verify.ps1`・`verify.sh`・`scripts/hooks/gate.py` | 変更していなければ新しい版に更新。ローカルで変更していれば **残します**（`KEEP-LOCAL`。`--force` で上書き） |
| 管理データの雛形 | `docs/requirements-definition.md`、`docs/catalog.md`、`docs/id-registry.md`、`docs/run-history.md`、`tests/system/ledger.json` | **ないときだけ**作ります。既存の文書は上書きしません |
| 設定 | `scripts/hve.config.json` | ないときは作成。あれば、新しい項目だけを足し、利用者の値は変えません |
| 追記 | `.gitignore` に `/work/`、`.gitattributes` に `docs/id-registry.md merge=union` と `docs/run-history.md merge=union` | 足りない行だけを追記します |
| ブロック | `AGENTS.md`、`.github/copilot-instructions.md` に `<!-- hve-conductor:begin -->`〜`end` の数行 | ブロックの中だけを置き換えます。ほかの記述は変えません |
| 記録 | `.github/hve-toolkit.json` | 版と、導入したファイルのハッシュ（更新・削除の判定に使います） |

導入の最後に `python scripts/verify.py --docs-only` を実行し、結果を表示します。

## 2.5 導入後にすること

1. 差分を確認して commit します。
   ```bash
   git add -A && git commit -m "Add conductor toolkit"
   ```
2. `scripts/hve.config.json` の `verify.commands` に、ビルド・静的検査・テストのコマンドを登録します（[07-customization.md](07-customization.md)）。空のままでも、初回の実行で implementer がその技術スタックの標準のコマンドを登録します。
3. CI でアプリのツールチェーン（Node.js など）が要る場合は、`.github/workflows/hve-verify.yml` の verify の前にセットアップの手順を足します。
4. 既存の要求定義書がある場合は、ID を ID 台帳に取り込みます。
   ```bash
   python scripts/next-id.py --sync --adopt
   ```
   そのうえで `python scripts/verify.py --docs-only --show-warnings` を実行し、構造化欄の不足（CHK-20）などを確認します。直すのは最初の実行で rd-author に任せてかまいません（依頼に「既存の要求定義書を toolkit の書式に合わせる」と書きます）。

## 2.6 更新・確認・削除

```bash
# 更新（同じ導入コマンドをもう一度実行するだけ）
curl -fsSL https://raw.githubusercontent.com/dahatake/HypervelocityEngineering/main/tools/install.sh | bash

# 更新が必要かだけを確かめる
curl -fsSL .../tools/install.sh | bash -s -- --check

# 削除（変更していない toolkit のファイルと、AGENTS.md などのブロックを外します。docs と台帳は残します）
curl -fsSL .../tools/install.sh | bash -s -- --uninstall
```

## 2.7 なぜ plugin ではなくインストーラーなのか

GitHub Copilot には、agents・skills・hooks をまとめて配る業界標準の仕組みとして **plugin**（`copilot plugin install OWNER/REPO`、Agent Plugins 仕様）があります。採用を検討しましたが、この toolkit の配布には使っていません。理由は次のとおりです。

| 観点 | plugin | この toolkit に必要なこと |
|---|---|---|
| 入る場所 | 利用者のホーム（プラグインのディレクトリ）。リポジトリには入らない | 決定的スクリプト（`scripts/`）、管理データの雛形（`docs/`）、台帳、`.gitignore`、CI を**対象のリポジトリの中**に置き、git で管理し、CI（GitHub Actions）でも同じ verify を実行する必要がある |
| 可搬性 | Agent Plugins 1.0 で可搬なのは skills と MCP だけで、custom agents と hooks はクライアントごとの拡張 | VS Code の Copilot harness・Copilot CLI・Copilot app で同じ `.github/agents`・`.github/skills`・`.github/hooks` を使う（計画書 A-1） |
| hook の範囲 | プラグインの hook は、利用者のすべてのリポジトリ・セッションで動く | ゲートは、この仕組みを導入したリポジトリでだけ動くべき |
| チームでの共有 | 利用者ごとにインストールが必要 | リポジトリを clone すれば、チーム全員と CI が同じ版を使える |

そのため、**リポジトリに `.github/` の customizations と `scripts/` を置く**（VS Code・Copilot CLI・Copilot app・cloud agent が標準で読む場所）方式にし、その導入・更新・削除を単一コマンドで行う `tools/install.*` を用意しました。

## 2.8 トラブル

| 症状 | 対処 |
|---|---|
| `Python 3.9 以上が必要です` | Python を入れ、`python --version` が通ることを確かめます |
| `git リポジトリではありません` | `git init -b main` してから実行します |
| `KEEP-LOCAL` が表示された | ローカルで変更したファイルは更新していません。差分を確認し、上書きしてよければ `--force` |
| hook の実行で `python` が見つからない | hook は `python3`（macOS/Linux）または `python`（Windows）を呼びます。PATH を確認します |
