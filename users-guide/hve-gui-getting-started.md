# HVE GUI Orchestrator はじめかた

← [README](../README.md)

> **対象読者**: ローカル PC（Windows / macOS / Linux）から GUI ウィザードでワークフローを実行したい初めての方
> **前提**: Python 3.11+ / Git / GitHub Copilot ライセンス
> **別の方式**: [hve-cloud-getting-started.md](./hve-cloud-getting-started.md)（Cloud）/ [hve-cli-getting-started.md](./hve-cli-getting-started.md)（CLI）

このガイドは、GUI Orchestrator を「動かしてみる」までの最小手順をまとめたチュートリアルです。GUI の各画面・全オプションの詳細は [hve-gui-orchestrator-guide.md](./hve-gui-orchestrator-guide.md) を参照してください。

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
| PySide6 >= 6.6 | 必須 | セットアップスクリプトで自動インストール |
| Git | 必須 | リポジトリ取得 |
| GitHub CLI (`gh`) | 必須 | `gh auth login` で認証 |
| GitHub Copilot ライセンス | 必須 | Copilot SDK の利用に必要 |

詳細は [hve-gui-orchestrator-guide.md の「前提条件」](./hve-gui-orchestrator-guide.md#前提条件) を参照してください。

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

Copilot ライセンスが付与されているアカウントでログインしてください。

### 3. `.venv` 作成 + GUI 依存をインストール

セットアップスクリプトに **GUI extras を含める** オプションを付けて実行します。

#### Windows

```cmd
hve\setup-hve.cmd
```

> `hve\setup-hve.cmd` は GUI extras（PySide6 等）を**既定で導入**します。ダブルクリックでも実行できます。

#### macOS / Linux

```bash
./hve/setup-hve.sh --with-gui
```

スクリプトの詳細・オプションは [hve-gui-orchestrator-guide.md の「インストール」](./hve-gui-orchestrator-guide.md#インストール) を参照してください。

### 4. GUI を起動して動作確認

```bash
python -m hve
```

引数なしの `python -m hve` は GUI ウィザードを起動します（PySide6 未導入時は CLI に自動フォールバック）。ウィンドウが開けばセットアップ完了です。

---

## クイックスタート（サンプルで動かしてみる）

リポジトリ同梱の `sample/business-requirement.md`（ロイヤルティプログラムの業務要件サンプル）を入力にして、**ARD（要求定義の自動化）ワークフロー**を GUI から実行します。

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

### 2. GUI を起動

```bash
python -m hve
```

または明示的に:

```bash
python -m hve gui
```

### 3. ウィザードで ARD を選択して実行

GUI は 3 ステップ構成です（詳細は [hve-gui-orchestrator-guide.md の「3 ステップ操作ガイド」](./hve-gui-orchestrator-guide.md#3-ステップ操作ガイド)）。

1. **ステップ 1: ワークフロー選択** — 一覧から **ARD（Auto Requirement Definition）** を選択
2. **ステップ 2: パラメータ入力**
   - `company-name`: `ロイヤルティサンプル` を入力
   - その他のオプションは既定値のままで OK
3. **ステップ 3: 実行確認** — 内容を確認して「実行」をクリック

実行が完了すると、以下のような成果物が生成・更新されます（詳細は [01-business-requirement.md](./01-business-requirement.md) 参照）。

- `docs/company-business-requirement.md`（企業・業務分析）
- `docs/business-requirement.md`（業務要件）
- `docs/catalog/use-case-catalog.md`（ユースケース一覧）

---

## ファイルツリー / Markdown プレビュー（左右パネル）

ステップ 2（実行画面）には、VS Code エクスプローラー風の **ファイルツリーパネル**（左）と **Markdown プレビューパネル**（右）が組み込まれています。Orchestrator 実行中に成果物の作成・更新を確認したいときに使います。

### パネルの開閉

ウィンドウ左端に縦に並んだ **アクティビティバー** から、トグルボタンで表示/非表示を切り替えます。

- 📁 ボタン: ファイルツリーパネル
- 📄 ボタン: Markdown プレビューパネル

既定では両方とも非表示です（中央のワークベンチを広く使えるように）。必要なときにボタンを押して開いてください。表示状態はセッション間で保持されます（`hve/.settings.txt`）。

### ファイルツリーパネル

以下のフォルダーがルートとして並びます（存在しないものは非表示）。

- `work/gui-runs/<セッションID>/` — このセッションが生成する全成果物
- `docs/` — 業務要件・設計成果物
- `knowledge/` — ドメイン知識・ADR
- `qa/` — 質問票・回答
- `docs-generated/` — 自動生成ドキュメント

**リアルタイム更新マーカー**: Orchestrator がファイルを新規作成・更新すると、ツリーの該当行の右端に小さな丸が約 5 秒間表示されます。
- 緑 ●: 新規作成
- 橙 ●: 内容更新

**操作**:
- 検索ボックスでファイル名フィルタ
- ファイルをクリック → 右のプレビューに表示
- 右クリック → 「パスをコピー」「エクスプローラで開く」

### Markdown プレビューパネル

選択したファイルをレンダリングして表示します。

- **対応形式**:
  - `.md` / `.markdown` 等 → Markdown レンダリング（見出し / 表 / リスト / コードブロック / 数式 / Mermaid 図）
  - `.py` / `.json` / `.yaml` 等 → Pygments によるシンタックスハイライト
  - その他テキスト → プレーン表示
  - バイナリ・2 MB 超 → 警告メッセージ
- **ライブ更新**: 表示中ファイルが書き換わると自動で再レンダリングされ、スクロール位置も維持されます。
- **外部リンク**: `http(s)://` リンクはクリックで OS 既定ブラウザに開きます。

> **Mermaid 図と数式（KaTeX）について**:
> 初期インストールではプレースホルダのみで、Mermaid / KaTeX アセット (`mermaid.min.js` / `katex.min.js` 等) は同梱されていません。配置手順は `hve/gui/markdown_preview/assets/LICENSE-third-party.md` を参照してください。未配置でも通常の Markdown はレンダリングされます。

### 既知の制約

- ファイル変更検出は `QFileSystemWatcher`（OS イベント）のみで実装しています。Windows / WSL / ネットワークドライブでは検知の取りこぼしが報告されているため、表示更新が遅れた場合は対象フォルダーを一度別ペインから開き直す（または GUI を再起動する）と最新状態を反映できます。
- プレビュー機能（`QWebEngineView`）の初回起動には数秒かかります（Chromium 初期化）。プレビューパネルを最初に開いたタイミングで初期化が走ります。

---

## 次のステップ

- **GUI Orchestrator の本格利用**: [hve-gui-orchestrator-guide.md](./hve-gui-orchestrator-guide.md)
- **要求定義ワークフローの詳細**: [01-business-requirement.md](./01-business-requirement.md)
- **別の方式を試す**: [hve-cloud-getting-started.md](./hve-cloud-getting-started.md) / [hve-cli-getting-started.md](./hve-cli-getting-started.md)
- **全体像の把握**: [README.md](../README.md)
- **トラブルシューティング**: [troubleshooting.md](./troubleshooting.md)
