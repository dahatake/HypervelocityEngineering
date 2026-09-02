# tools/for-other-repo — 他リポジトリへの配布

`markdown-query` / `code-query` / `tool-search` を、このリポジトリ以外でも使えるように
まとめて配布するための場所。**手動同期**を前提にしている（CI から自動 push しない）。

```pwsh
# 一覧
python tools/for-other-repo/copy_to_repo.py --list

# 3 つ全部を D:\other-repo\tools\hve-kits\ へコピー
python tools/for-other-repo/copy_to_repo.py D:\other-repo\tools\hve-kits

# 1 つだけ
python tools/for-other-repo/copy_to_repo.py D:\other-repo\tools\hve-kits -p tool-search

# コピー先の版と改変状況だけ確認（書き込まない）
python tools/for-other-repo/copy_to_repo.py D:\other-repo\tools\hve-kits --check
```

macOS / Linux は `bash tools/for-other-repo/copy-to-repo.sh <コピー先>`、
Windows は `pwsh -NoLogo -NoProfile -File tools/for-other-repo/copy-to-repo.ps1 <コピー先>` でもよい。

---

## 1. 設計方針 — 実体を二重に持たない

エンジン本体（`mdq` / `cq` / `toolsearch`）も、Skill 定義も、セットアップの共通実装も、
このリポジトリの既存の場所に既に版管理下で存在する。ここではそれらを**複製しない**。

`<package>/package.toml` が「どこから何を集めるか」だけを宣言し、
[`copy_to_repo.py`](./copy_to_repo.py) がコピー時に組み立てる。

| パッケージ | 集める元 |
|---|---|
| `markdown-query` | `tools/skills/markdown_query/`（エンジン・Skill・共通 setup を同梱済み）+ `users-guide/skills-markdown-query.md` |
| `code-query` | `tools/skills/code_query/`（同上）+ `users-guide/skills-code-query.md` |
| `tool-search` | `hve/toolsearch/` + `mdq/tokenize.py` + `tools/skills/_kit/` + `users-guide/tool-search.md` |

規範は要件定義の **FR-KIT-06**（宣言の単一化と版管理）。検証は
[hve/tests/test_for_other_repo_sync.py](../../hve/tests/test_for_other_repo_sync.py)。

`tool-search` だけは上流に配布キットが無いため、CLI 入口
（[`tool-search/engine/cli.py`](./tool-search/engine/cli.py)）と実行ラッパーを
ここで用意している。上流ではこの役目を `hve/__main__.py` の
`toolsearch dashboard` サブコマンドが担っている。

---

## 2. 配布物の構成

コピー先には `<コピー先>/<パッケージ名>/` が作られる。

```
<コピー先>/markdown-query/
  install.ps1 / install.sh      OS だけの状態から実行できるセットアップ入口
  install.py                    セットアップ引数の組み立て（kit/kit_setup.py へ委譲）
  install-extras.json           配布先で追加導入する pip パッケージ（宣言があるときだけ）
  kit/kit_setup.py              venv・依存・設定生成・Skill 配置の単一実装（上流と同一）
  vendor/mdq/                   エンジン本体
  skill/                        .github/skills/ へ配置される Skill 定義
  docs/                         users-guide から同梱したドキュメント
  GETTING-STARTED.md            導入手順
  KIT-VERSION.json              版マニフェスト（copy_to_repo.py が生成）
```

`install.ps1` / `install.sh` の責務は 2 つだけ:

1. Python 3.11+ と git が無ければ OS のパッケージマネージャで導入する
   （Windows: winget → choco / macOS: Homebrew / Linux: apt・dnf・yum・zypper・pacman・apk）
2. 以降の判断を `install.py` → `kit/kit_setup.py` へ委譲する

OS 別スクリプトに判断ロジックを持たせない方針は上流の `tools/skills/_kit/` と同じ。

### 追加依存（`extra_dependencies`）

上流では `pip install -e .[code]` のような extras で入る依存が、配布先には存在しない。
`package.toml` の `extra_dependencies` に挙げると `install-extras.json` として同梱され、
`install.py` が kit の venv へ先に導入してから `kit/kit_setup.py` を呼ぶ。

`code-query` は tree-sitter 文法群がこれに当たる。未導入でも索引は成立する（lite へ降格）が、
shell / PowerShell / batch / Scala / SQL は終了行・doc・参照・構造チャンクを失うため既定で導入する。
wheel が無い環境では `--no-extras` で省略できる。

---

## 3. 版管理

コピー時に `<パッケージ>/KIT-VERSION.json` が生成される。

| キー | 内容 |
|---|---|
| `version` | `package.toml` の `package.version`（配布パッケージとしての版） |
| `engine_version` | 同梱エンジンの `__version__`（取得できない場合は `version` と同じ） |
| `source_commit` | 上流リポジトリの短縮 commit hash（git が使えないときは `null`） |
| `copied_at` | コピー時刻（UTC） |
| `files` | 配布した全ファイルの `sha256`。改変・欠落の検出に使う |
| `preserved` | 利用者が編集する前提のファイル。上書きしないし、改変検出の対象ともしない |

コピー先だけで確認する場合（上流リポジトリを参照しない）:

```pwsh
python <コピー先>\<パッケージ>\install.py --kit-dir <コピー先>\<パッケージ> --version
python <コピー先>\<パッケージ>\install.py --kit-dir <コピー先>\<パッケージ> --verify
```

判定は次のとおり。

| コピー先の版 | 挙動 |
|---|---|
| 未導入 | `new` としてコピー |
| 上流より古い | `upgrade` としてコピー |
| 上流と同じ | `same`。スキップ（`--force` で上書き） |
| 上流より新しい | `downgrade`。スキップ（`--force` で上書き） |

コピー時には、前回の `files` に含まれていて今回含まれないファイルを削除する
（配布物として自分が置いたものだけを消す。利用者が作った venv や設定は消さない）。
`package.toml` の `preserve` に挙げたファイルは、既に存在するなら上書きしない
（例: `tool-search` の `vendor/toolsearch/policy.json`）。

版を上げるときは `<package>/package.toml` の `package.version` を編集する。

---

## 4. 変更を反映する手順

1. 上流の実装（`mdq/` / `cq/` / `hve/toolsearch/`）を直す
2. `markdown-query` / `code-query` は上流キットの `sync-vendor.ps1` / `sync-vendor.sh` で
   `vendor/` を更新する（`tool-search` はコピー時に直接集めるため不要）
3. `<package>/package.toml` の `package.version` を上げる
4. `copy_to_repo.py <コピー先>` で各リポジトリへ同期する

---

## 5. 制約

- 配布先で動くのはローカル完結の機能のみ。外部 API へは接続しない。
- `code-query` は `git` が必須（`git ls-files` でファイルを列挙するため）。
- `tool-search` は Copilot SDK を呼ぶアプリケーション側へ組み込むライブラリであり、
  Skill 定義は同梱しない。詳細は [`tool-search/GETTING-STARTED.md`](./tool-search/GETTING-STARTED.md)。
- 同梱ドキュメント内のリンクの一部は上流リポジトリのパスを指し、配布先では解決しない。
