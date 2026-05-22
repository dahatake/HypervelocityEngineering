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

スクリプトは `.venv` 作成 + `github-copilot-sdk` + `[mdq]` extras をインストールします。詳細・オプション（`--with-gui` 等）は [hve-cli-orchestrator-guide.md の「セットアップスクリプトを使った環境構築」](./hve-cli-orchestrator-guide.md#セットアップスクリプトを使った環境構築windows--macos--linux) を参照してください。

### 4. 動作確認

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

## 次のステップ

- **CLI Orchestrator の本格利用**: [hve-cli-orchestrator-guide.md](./hve-cli-orchestrator-guide.md)
- **要求定義ワークフローの詳細**: [01-business-requirement.md](./01-business-requirement.md)
- **別の方式を試す**: [hve-cloud-getting-started.md](./hve-cloud-getting-started.md) / [hve-gui-getting-started.md](./hve-gui-getting-started.md)
- **全体像の把握**: [README.md](../README.md)
- **トラブルシューティング**: [troubleshooting.md](./troubleshooting.md)
