# HVE CLI Orchestrator はじめかた

← [README](../README.md)

> **対象読者**: ローカル PC（Windows / macOS / Linux）から `python -m hve` でワークフローを実行したい初めての方
> **前提**: Python 3.11+ / Git / GitHub Copilot ライセンス
> **別の方式**: [hve-cloud-getting-started.md](./hve-cloud-getting-started.md)（Cloud）/ [hve-gui-getting-started.md](./hve-gui-getting-started.md)（GUI）

このガイドは、CLI Orchestrator を「動かしてみる」までの最小手順をまとめたチュートリアルです。詳細仕様・全オプションは [hve-cli-orchestrator-guide.md](./hve-cli-orchestrator-guide.md) を参照してください。

---

## 目次

- [前提条件](#前提条件)
- [セットアップ手順](#セットアップ手順)
- [クイックスタート（サンプルで動かしてみる）](#クイックスタートサンプルで動かしてみる)
- [完了確認と失敗時対応](#完了確認と失敗時対応)
- [HVE をカスタマイズする方への入口](#hve-をカスタマイズする方への入口)
- [HVE パッケージのバージョン管理](#hve-パッケージのバージョン管理)
- [次のステップ](#次のステップ)

---

## 前提条件

| ツール | 必須 / 任意 | メモ |
|---|---|---|
| Python 3.11+ | 必須 | `py -3.11 --version` または `python3 --version` で確認 |
| Git | 必須 | リポジトリ取得 |
| GitHub CLI (`gh`) | 必須 | `gh auth login` で認証 |
| GitHub Copilot ライセンス | 必須 | Copilot SDK の利用に必要 |
| Node.js / npx | 任意 | MCP Server を使う場合のみ |

詳細な必須/任意ツール一覧は [hve-cli-orchestrator-guide.md の「必須 / 任意ツール早見表」](./hve-cli-orchestrator-guide.md#必須--任意ツール早見表) を参照してください。

---

## セットアップ手順

### 1. リポジトリを取得（クローン済みの場合はスキップ）

```bash
git clone https://github.com/<owner>/<repo>.git
cd <repo>
```

### 2. GitHub CLI で認証

```bash
gh auth login
```

ブラウザが開くので画面の指示に従ってください。Copilot ライセンスが付与されているアカウントでログインします。

### 3. `.venv` 作成と依存パッケージのインストール

セットアップスクリプトを使うのが最短です。

#### Windows

```cmd
hve\setup-hve.cmd
```

> ダブルクリックでも実行できます。

#### macOS / Linux

```bash
./hve/setup-hve.sh
```

スクリプトは `.venv` 作成 + `github-copilot-sdk` + 全 extras（`test` / `mdq-watch` / `mdq-ja` / `semantic` / `code-watch` / `code-tokenizer` / `code-semantic` / `gui` / `gui-pty` / `gui-docconvert`）を既定でインストールします。`test` は repository / VS Code task 検証用の pytest を含みます。CLI のみで良い場合は `--no-gui`、runtime baseだけにしたい場合は `--minimal` を付けてください。詳細・オプションは [hve-cli-orchestrator-guide.md の「セットアップスクリプトを使った環境構築」](./hve-cli-orchestrator-guide.md#セットアップスクリプトを使った環境構築windows--macos--linux) を参照してください。

### code-query の文法を言語で絞る

既定では `code-query`（`cq`）が対応する全言語の tree-sitter 文法を導入します。使う言語だけに絞りたい場合は言語名をカンマ区切りで渡してください。

```powershell
hve\setup-hve.cmd -CodeLanguages python,csharp,powershell
```

```bash
./hve/setup-hve.sh --code-languages python,csharp,powershell
```

指定できる言語名: `python` / `csharp` / `javascript` / `typescript` / `java` / `go` / `rust` / `c` / `cpp` / `scala` / `shell` / `powershell` / `batch` / `sql`。未知の言語名を渡すとインストールせずにエラー終了します。`--minimal` と併用した場合は文法を一切入れないため、この指定は警告付きで無視されます。導入しなかった言語は低フィデリティのパーサへ降格するだけで、索引そのものは失敗しません（詳細は [skills-code-query.md §7.1](./skills-code-query.md#71-必要な言語だけ導入する)）。

> **Python 自動インストールと管理者権限について**
>
> Python 3.11+ が見つからない場合、セットアップスクリプトは **最新の Python 3.14 を自動インストール**しようとします。OS ごとに以下の権限が必要になる場合があります:
>
> | OS | 使用するパッケージマネージャ | 権限 |
> |---|---|---|
> | Windows | `winget`（`--scope user` でユーザー領域へインストール） | 通常は不要。winget 自体が UAC（管理者承認）を要求する場合あり |
> | macOS | Homebrew (`brew install python@3.14`) | **sudo 不要**（Homebrew がユーザー prefix を所有している場合） |
> | Ubuntu / Debian | `apt` + deadsnakes PPA | **sudo 必要**（`sudo apt-get` / `sudo add-apt-repository`） |
> | Fedora / RHEL | `dnf` | **sudo 必要** |
> | Arch Linux | `pacman` | **sudo 必要** |
>
> 自動インストール前に確認プロンプトが表示されます。確認を省略するには `-Yes`（Windows）/ `--yes`（macOS/Linux）を、自動インストールを完全に無効化するには `-NoInstallPython` / `--no-install-python` を指定してください。winget や Homebrew 自体が未インストールの環境では、エラーメッセージに従って手動で導入してください。
>
> **PowerShell 7+ 必須（Windows）**
>
> `setup-hve.cmd` / `setup-hve.ps1` は **PowerShell 7+（pwsh.exe）が必須**です。Windows 同梱の Windows PowerShell 5.x は非対応（ネイティブコマンド引数の二重引用符処理が異なるため）。pwsh が未インストールの場合、`setup-hve.cmd` は **winget で自動インストール**を試みます（`--scope user` でユーザー領域、UAC 要求が発生する場合あり）。手動導入は `winget install --id Microsoft.PowerShell -e --source winget` または https://aka.ms/install-powershell を参照してください。

### 4. GitHub Copilot SDK で認証

HVE の Step 実行は GitHub Copilot SDK を使います。初回、または認証が切れたときに実行します。

```bash
python -m hve login
```

認証状態と、キャッシュ済みモデル一覧だけを確認したい場合はログインを起動せずに確認できます。

```bash
python -m hve login --status
```

> 主なオプション（正本: `hve/__main__.py` の `login` パーサー）
>
> | オプション | 既定 | 用途 |
> |---|---|---|
> | `--host` | `https://github.com` | GHEC データレジデンシー利用時のみ変更 |
> | `--skip-fetch` | 無効 | ログイン後のモデル一覧取得をスキップ |
> | `--status` | 無効 | ログインを起動せず現在の認証状態を表示 |

### 5. 動作確認

```bash
python -m hve --help
```

`hve` のヘルプが表示されればセットアップ完了です。

---

## クイックスタート（サンプルで動かしてみる）

リポジトリ同梱の `sample/business-requirement.md`（ロイヤルティプログラムの業務要件サンプル）を入力にして、**ARD（要求定義の自動化）ワークフロー**を 1 回実行します。

### 1. サンプル業務要件を `docs/` にコピー

> **注意**: ARD ワークフローは `docs/business-requirement.md` を出力するため、コピーしたサンプルは **ARD 実行時にワークフロー成果物で上書きされます**。サンプルを保持したい場合は別名で残してください。

#### Windows (PowerShell)

```powershell
Copy-Item sample\business-requirement.md docs\business-requirement.md
```

#### Windows (cmd)

```cmd
copy sample\business-requirement.md docs\business-requirement.md
```

#### macOS / Linux

```bash
cp sample/business-requirement.md docs/business-requirement.md
```

### 2. dry-run で疎通確認

実際に Copilot を呼ばずに DAG だけを表示します。

```bash
python -m hve orchestrate --workflow ard --dry-run
```

エラーなく DAG が表示されればセットアップは正常です。

### 3. ARD を実行

```bash
python -m hve orchestrate --workflow ard --company-name "ロイヤルティサンプル"
```

実行が完了すると、以下のような成果物が生成・更新されます（詳細は [01-business-requirement.md](./01-business-requirement.md) 参照）。

- `docs/company-business-requirement.md`（企業・業務分析）
- `docs/business-requirement.md`（業務要件）
- `docs/catalog/use-case-catalog.md`（ユースケース一覧）

### 4. インタラクティブモード（任意）

オプションをコマンドに書かずに、対話形式で実行したい場合:

```bash
python -m hve cli
```

ワークフローやパラメータを wizard が順に尋ねます。

---

## 完了確認と失敗時対応

### 完了確認

| 段階 | 確認方法 | 期待結果 |
|---|---|---|
| 環境構築 | `python -m hve --help` | サブコマンド一覧が表示される |
| SDK 認証 | `python -m hve login --status` | 認証済みとして表示される |
| 疎通 | `python -m hve orchestrate --workflow ard --dry-run` | Copilot を呼ばずに DAG が表示される |
| 実行 | ARD 実行後に `docs/` を確認 | 上記 3 つの成果物が生成・更新されている |

### 失敗時対応

| 症状 | 最初に確認すること | 対応 |
|---|---|---|
| `python -m hve` が動かない | `.venv` の有効化と依存導入 | セットアップスクリプトを再実行する。詳細は [hve-cli-orchestrator-guide.md の付録D](./hve-cli-orchestrator-guide.md#付録d-トラブルシューティング) |
| 認証エラーになる | `gh auth status` と `python -m hve login --status` | `gh auth login` と `python -m hve login` をやり直す |
| Windows でセットアップが失敗する | PowerShell 7+（`pwsh`）の有無 | `setup-hve.cmd` は PowerShell 7+ が必須。未導入なら winget で導入する |
| dry-run は通るが実行が止まる | Copilot ライセンスとモデル選択 | ライセンス付与済みアカウントか確認する。詳細は [troubleshooting.md](./troubleshooting.md) |
| 成果物が生成されない | 実行ログの Step 単位の結果 | 失敗した Step のログを確認する。ログ量は `--verbosity` / `--log-level` で調整できる |

網羅的な事例は [troubleshooting.md](./troubleshooting.md) と [hve-cli-orchestrator-guide.md の付録D](./hve-cli-orchestrator-guide.md#付録d-トラブルシューティング) を参照してください。

---

## HVE をカスタマイズする方への入口

このチュートリアルは「動かす」までを対象にしています。HVE 自身を変更する場合の正本は次のとおりです。

| 変更したいもの | 正本 |
|---|---|
| CLI サブコマンド・引数 | `hve/__main__.py` |
| 設定値・既定値・環境変数 | `hve/config.py` |
| ワークフロー定義（Step・Custom Agent・成果物） | `hve/workflow_registry.py` |
| セットアップスクリプトの挙動 | `hve/setup-hve.ps1` / `hve/setup-hve.sh` / `hve/setup-hve.cmd` |
| 依存パッケージと extras | `pyproject.toml` |
| HVE パッケージ版と変更履歴 | `pyproject.toml` / `hve/__init__.py` / `CHANGELOG.md` |

### HVE パッケージのバージョン管理

HVE の実装または実行契約を変更するジョブでは、完了報告前に**必ず** HVE パッケージ版と `CHANGELOG.md` を同じ変更セットで更新します。対象には `hve/**`、`hve-dev/**`、HVE を駆動する Prompt / Skill / Workflow / I/O 契約、HVE 用テンプレート、実行設定・スクリプトが含まれます。変更履歴または版番号の同期だけを行う変更は、追加の版上げを必要としません。独立ライフサイクルで版管理する `mdq/**` / `cq/**` / 配布キットは本手順の対象外で、それぞれの版管理手順に従います。

**HVE が設計・開発する別アプリケーションには適用されません。** `src/**`、`docs/**`、`docs-generated/**`、`knowledge/**`、`qa/**`、`package.json` 等の生成アプリ成果物、および生成アプリのデプロイ workflow（`.github/workflows/deploy-*.yml` / `azure-static-web-apps-*.yml` / `app<数字>*.yml`）だけを変更した場合、HVE の版を上げる必要はありません。境界の機械判定は [.github/scripts/hve_scope.py](../.github/scripts/hve_scope.py) が単一の正本です。

| 判断 | 実施内容 |
|---|---|
| 通常の HVE 関連変更 | PATCH（`x.y.z` の `z`）をジョブごとに 1 回だけ増やす |
| MINOR 更新 | `x.y.0` の `y` を増やすのは、**ユーザーが明示的に判断した場合のみ**。Copilot は自律的に更新しない |
| 版番号の同期 | `pyproject.toml` の `[project].version` と `[tool.bumpversion].current_version`、`hve/__init__.py` の `__version__`、`CHANGELOG.md` の版見出しを同じ値にする |
| 変更履歴 | 変更点・影響・検証結果を記載する。既存の `[Unreleased]` エントリーは別作業として保持し、その内容の後ろへ新しい版見出しを追加して誤って新しいリリースへ移さない |

この運用の Copilot 向け正本は `.github/copilot-instructions.md` の「HVE の版管理と変更履歴」です。版上げ後は、少なくとも 3 か所の版番号の一致、変更履歴への記載、関連する静的検証またはテストを確認してください。

変更後は関連テストで回帰を確認してください。

```bash
python -m pytest hve/tests/test_cli_login.py
```

手順の詳細とカスタマイズ観点は [hve-cli-orchestrator-guide.md](./hve-cli-orchestrator-guide.md) を参照してください。

---

## 次のステップ

- **CLI Orchestrator の本格利用**: [hve-cli-orchestrator-guide.md](./hve-cli-orchestrator-guide.md)
- **ローカルから CI/CD を有効化する**: [local-cicd-enablement.md](./local-cicd-enablement.md)
- **要求定義ワークフローの詳細**: [01-business-requirement.md](./01-business-requirement.md)
- **別の方式を試す**: [hve-cloud-getting-started.md](./hve-cloud-getting-started.md) / [hve-gui-getting-started.md](./hve-gui-getting-started.md)
- **Step を Cloud Session で実行する**: [cloud-session.md](./cloud-session.md)
- **全体像の把握**: [README.md](../README.md)
- **トラブルシューティング**: [troubleshooting.md](./troubleshooting.md)

---

## 公式出典

- Install GitHub Copilot CLI — <https://docs.github.com/en/copilot/how-tos/set-up/install-copilot-cli>
- github/copilot-sdk（リポジトリ） — <https://github.com/github/copilot-sdk>
- Install PowerShell on Windows — <https://learn.microsoft.com/powershell/scripting/install/installing-powershell-on-windows>
