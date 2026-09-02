# markdown-query — 他リポジトリでの導入手順

ローカル完結で Markdown 群を横断検索し、ヒット箇所の小さな snippet だけを返す Skill。
Copilot / Custom Agent の Context Window 消費を最小化することが唯一の目的で、外部 API は呼び出さない。

このフォルダは上流リポジトリ（`dahatake/RoyalytyService2ndGen`）の
`tools/skills/markdown_query/` を `tools/for-other-repo/copy_to_repo.py` でコピーしたもの。
同梱の版情報は [`KIT-VERSION.json`](./KIT-VERSION.json) にある。

---

## 1. セットアップ（OS だけの状態から）

導入先リポジトリの**ルート**で実行する。`install.ps1` / `install.sh` が
Python 3.11+ と git を確認し、無ければ OS のパッケージマネージャで導入してから
venv 作成・依存インストール・`mdq.toml` 生成・Skill 配置・初回索引まで行う。

### Windows

```pwsh
pwsh -NoLogo -NoProfile -File <このフォルダ>\install.ps1
```

### macOS / Linux

```bash
bash <このフォルダ>/install.sh
```

### 主なオプション

| オプション | 意味 |
|---|---|
| `-WithGui` / `--with-gui` | 設定 GUI（PySide6）も入れる |
| `-WithWatch` / `--with-watch` | ファイル監視（watchdog）による増分索引を入れる |
| `-WithTokenizer` / `--with-tokenizer` | `tiktoken` を入れてトークン計測を正確にする |
| `-NoIndex` / `--no-index` | 初回索引を省略する |
| `-NoSkill` / `--no-skill` | `.github/skills/markdown-query/` への配置を省略する |
| `-Force` / `--force` | 既存の `mdq.toml` / Skill 定義を再生成する |
| `-RepoRoot` / `--repo-root` | 導入先リポジトリのルート（既定: カレント） |

導入されるもの:

- `<repo>/mdq.toml` — 索引対象ルートの設定（既存なら温存。`--force` で再生成）
- `<repo>/.github/skills/markdown-query/` — Skill 定義（Copilot が読む）
- `<repo>/.mdq/` — SQLite 索引（初回索引時に生成）
- `<このフォルダ>/.venv-mdq-gui/` — 依存を隔離した venv

---

## 2. 使い方

```pwsh
# Windows
.\mdq.ps1 index
.\mdq.ps1 search --q "デプロイ手順"
.\mdq.ps1 stats
```

```bash
# macOS / Linux
./mdq.sh index
./mdq.sh search --q "デプロイ手順"
./mdq.sh stats
```

GUI 設定画面:

```pwsh
pwsh -NoLogo -NoProfile -File launch-gui.ps1     # Windows
bash launch-gui.sh                               # macOS / Linux
```

`.md` を変更したら `index` を再実行する（`--with-watch` を入れた場合は `watch` で自動追従）。

---

## 3. ドキュメント

| ファイル | 内容 |
|---|---|
| [`docs/skills-markdown-query.md`](./docs/skills-markdown-query.md) | 技術アーキテクチャ / Chunking Strategy / 利用統計 15 指標（`users-guide` から同梱） |
| [`skill/SKILL.md`](./skill/SKILL.md) | Skill 仕様本体（`.github/skills/` へ配置される正本） |
| [`skill/references/`](./skill/references/) | CLI リファレンス・索引内部仕様・クエリルーティング |
| [`README.md`](./README.md) | ベンチマーク（トークン削減率の計測）の使い方 |
| [`USAGE.md`](./USAGE.md) | GUI 設定画面の操作 |

> 同梱ドキュメント内のリンクの一部は上流リポジトリのパスを指す。
> そのリンク先は上流リポジトリでのみ解決する。

---

## 4. 更新（版の同期）

現状確認はこのフォルダだけでできる。

```pwsh
python install.py --kit-dir . --version    # 導入済みの版
python install.py --kit-dir . --verify     # 同梱ファイルの改変・欠落
```

更新は上流リポジトリ側で実行する。

```pwsh
# 上流との差分確認（コピーせず、版と改変状況だけ表示）
python tools/for-other-repo/copy_to_repo.py <コピー先> -p markdown-query --check

# 更新
python tools/for-other-repo/copy_to_repo.py <コピー先> -p markdown-query
```

`KIT-VERSION.json` に記録された版より上流が新しいときだけコピーされる。
同版・古い版を上書きするには `--force` を付ける。

---

## 5. 既知の制約

- 索引対象は `.md` と `mdq.toml` の `tabular` に列挙した表形式ファイルのみ。ソースコードは `code-query` の担当。
- `rank_bm25` 未導入時は内蔵の簡易 BM25 へ、`tiktoken` 未導入時は `chars/4` 近似へ降格する。
- GUI は PySide6 に依存する。`--with-gui` を付けなかった場合は起動しない。
